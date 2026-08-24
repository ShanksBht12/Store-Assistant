# E-Commerce Voice Agent — Project Plan
STT → LLM (with SQLite tool-calling) → TTS, fully model-configurable

---

## 1. Project Goal

Build a voice agent that:
1. Listens to a user speaking (Nepali-focused STT).
2. Converts speech to text.
3. Sends text to an LLM that can query a SQLite e-commerce database via tool/function calling.
4. Converts the LLM's answer back to speech.
5. Lets you **swap any model in any stage (STT / LLM / TTS) via config, with no code changes**.

Three teams own one stage each, but everyone builds against shared, versioned interfaces defined in Section 4 — this is what lets the teams work in parallel without blocking each other.

---

## 2. High-Level Architecture

```
                 ┌─────────────────────────────────────────────────────────┐
                 │                      GATEWAY / ORCHESTRATOR                │
                 │   (routes audio → STT → LLM → TTS, manages session state)  │
                 └─────────────────────────────────────────────────────────┘
                        │                    │                    │
          ┌─────────────▼───────┐  ┌─────────▼──────────┐ ┌───────▼─────────┐
          │     STT SERVICE       │  │    LLM + DB SERVICE  │ │   TTS SERVICE     │
          │  (Team 1)              │  │    (Team 2)           │ │   (Team 3)         │
          │                        │  │                        │ │                    │
          │ Audio in → Text out    │  │ Text in → tool calls  │ │ Text in → Audio out│
          │                        │  │  → SQLite query        │ │                    │
          │ Providers:              │  │  → Text out            │ │ Providers:          │
          │  - indicconformer_ne    │  │                        │ │  - ElevenLabs       │
          │  - "sravaani"           │  │ Providers:              │ │  - Camb.ai          │
          │  - (pluggable more)     │  │  - local LLM (Ollama)   │ │  - (pluggable more) │
          │                        │  │  - hosted API (Claude/  │ │                    │
          │                        │  │    OpenAI/etc)          │ │                    │
          └────────────────────────┘  └────────────────────────┘ └────────────────────┘
```

**Flow for one turn:**
`mic audio → STT service → transcript → LLM service (reads schema, decides to call a DB tool, executes SQL, gets rows, drafts reply) → reply text → TTS service → audio → playback`

### Two build modes
- **MVP (recommended start):** modular monolith — all 3 stages are Python packages with clean interfaces, run in one process, called directly. Fastest to build and debug.
- **Scale-up (later):** each stage becomes its own FastAPI microservice + Docker container, talking over REST/gRPC, coordinated by the gateway. Same interfaces, no rewrite — just move the code behind an HTTP boundary.

Start MVP, but write it so Section 4's interfaces are respected from day one — that's what makes the later split free.

---

## 3. Configurability — Core Design Pattern

Every stage (STT/LLM/TTS) follows the same pattern: **abstract base class + provider implementations + registry + YAML config.**

```python
# base.py (shared pattern, shown for STT — same shape for LLM and TTS)
from abc import ABC, abstractmethod

class BaseSTTProvider(ABC):
    @abstractmethod
    def load(self, **params): ...

    @abstractmethod
    def transcribe(self, audio_bytes: bytes, sample_rate: int) -> dict:
        """Returns {"text": str, "confidence": float, "duration_ms": int}"""
        ...
```

```python
# registry.py
STT_PROVIDERS = {}

def register_stt(name):
    def wrapper(cls):
        STT_PROVIDERS[name] = cls
        return cls
    return wrapper

def get_stt_provider(config: dict) -> BaseSTTProvider:
    name = config["stt"]["provider"]
    provider_cls = STT_PROVIDERS[name]
    instance = provider_cls()
    instance.load(**config["stt"][name])
    return instance
```

```python
@register_stt("indicconformer")
class IndicConformerSTT(BaseSTTProvider):
    def load(self, hf_model_id, device="cpu", decoding="rnnt", **_):
        import nemo.collections.asr as nemo_asr
        # Expensive step (~3 min per the vendor guide) — runs once at service
        # startup, never per-request. See Section 6 for the readiness-probe note.
        # EncDecHybridRNNTCTCBPEModel — this checkpoint supports BOTH decoders
        # despite "rnnt" being the only thing in its repo name (see Section 8, item 7)
        self.model = nemo_asr.models.EncDecHybridRNNTCTCBPEModel.from_pretrained(hf_model_id)
        self.model = self.model.to(device)
        self.model.change_decoding_strategy(decoder_type=decoding)  # "rnnt" for streaming, "ctc" for batch-only

    def transcribe(self, audio_bytes, sample_rate=16000):
        import soundfile as sf, tempfile, os
        # NeMo's transcribe() takes file paths, not raw bytes/arrays directly
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            sf.write(tmp.name, audio_bytes, sample_rate)
            text = self.model.transcribe([tmp.name])[0]
        os.unlink(tmp.name)
        # NeMo's basic transcribe() doesn't return confidence/duration —
        # leave as None until Team 1 adds custom scoring, or drop the fields
        return {"text": text, "confidence": None, "duration_ms": None}

@register_stt("sravaani")
class SravaaniSTT(BaseSTTProvider):
    def load(self, hf_model_id="ARTPARK-IISc/SraVaani-1.0", device="cpu", **_):
        import torch
        from transformers import AutoModel
        # trust_remote_code=True runs Python code shipped inside the model
        # repo, not just weights — pin an exact revision (see Section 8)
        # rather than tracking "main"
        self.model = AutoModel.from_pretrained(
            hf_model_id, trust_remote_code=True
        ).to(device).eval()

    def transcribe(self, audio_bytes, sample_rate=16000):
        import soundfile as sf, tempfile, os
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            sf.write(tmp.name, audio_bytes, sample_rate)
            result = self.model.transcribe(tmp.name, return_hypotheses=True)
        os.unlink(tmp.name)
        # Note the different raw return shape vs. NeMo's plain string —
        # this is exactly why the BaseSTTProvider contract exists: both
        # providers normalize down to the same {"text", "confidence", ...} dict
        text = result[0].text if result else ""
        return {"text": text, "confidence": None, "duration_ms": None}
```

This is the same load-once-transcribe-many pattern the IndicConformer integration guide calls out explicitly — loading the model per-request is the single most common mistake (it costs ~3 minutes each time), so `load()` must only ever run at service startup.

The exact same `register_llm` / `register_tts` pattern applies to Teams 2 and 3. **Adding a new model = writing one class + one config block, never touching the orchestrator.**

### `config.yaml` (single source of truth)

```yaml
language: ne          # ne = Nepali, en = English, used across all 3 stages

stt:
  provider: indicconformer      # switch to "sravaani" to change models
  indicconformer:
    hf_model_id: ai4bharat/indicconformer_stt_ne_hybrid_rnnt_large   # despite the name, this repo IS the hybrid CTC+RNNT checkpoint — see Section 8, item 7
    hf_token_env: HF_TOKEN        # token pulled from env/secrets manager at load time — never hardcoded, never baked into a Docker image
    device: cuda                  # falls back to cpu if no GPU is present
    sample_rate: 16000
    decoding: rnnt                # runtime decoder_type on the hybrid model, not a different checkpoint — rnnt is required for streaming, ctc is a faster batch-only alternative
  sravaani:
    hf_model_id: ARTPARK-IISc/SraVaani-1.0
    hf_token_env: HF_TOKEN        # SraVaani also requires HF auth to download
    device: cuda                   # GPU: ~2-5s/file; CPU: ~10-30s/file per vendor guide — meaningfully slower profile than IndicConformer
    trust_remote_code: true        # required by this model's architecture — see Section 8
    revision: <pin-a-commit-hash>  # never leave unpinned/tracking "main" when trust_remote_code is true

llm:
  provider: anthropic            # options: anthropic, openai, ollama_local, groq
  anthropic:
    model: claude-sonnet-5
    api_key_env: ANTHROPIC_API_KEY
    max_tokens: 1024
  openai:
    model: gpt-4.1
    api_key_env: OPENAI_API_KEY
  ollama_local:
    model: llama3.1:8b
    base_url: http://localhost:11434

tts:
  provider: elevenlabs           # options: elevenlabs, camb
  elevenlabs:
    api_key_env: ELEVENLABS_API_KEY
    voice_id: xxxxxxxx
    model_id: eleven_multilingual_v2
  camb:
    api_key_env: CAMB_API_KEY
    voice_id: xxxxxxxx

db:
  path: ./data/ecommerce.db
```

Switching any model at any stage = editing one line (`provider:`) + filling in that provider's block. No code touched.

---

## 4. Interfaces Between Teams (contract, freeze this first)

Define these on day 1 so all three teams can build against mocks immediately, in parallel.

| Stage | Input | Output |
|---|---|---|
| **STT** | `POST /stt/transcribe` — raw audio bytes (wav/pcm), sample rate, language | `{"text": str, "confidence": float, "duration_ms": int}` |
| **LLM+DB** | `POST /llm/chat` — `{"text": str, "session_id": str, "language": str}` | `{"reply_text": str, "tool_calls": [ {name, args, result} ], "session_id": str}` |
| **TTS** | `POST /tts/synthesize` — `{"text": str, "language": str, "voice": str}` | `{"audio_base64": str, "format": "mp3/wav", "duration_ms": int}` |

Everyone codes to these JSON shapes. Even in the monolith, call the modules through these function signatures — this is what makes the later microservice split a non-event.

---

## 5. Database Design (dummy e-commerce data)

```sql
CREATE TABLE products (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    category TEXT NOT NULL,
    price REAL NOT NULL,
    stock INTEGER NOT NULL,
    description TEXT
);

CREATE TABLE customers (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    phone TEXT,
    email TEXT,
    address TEXT
);

CREATE TABLE orders (
    id INTEGER PRIMARY KEY,
    customer_id INTEGER REFERENCES customers(id),
    product_id INTEGER REFERENCES products(id),
    quantity INTEGER NOT NULL,
    status TEXT CHECK(status IN ('pending','shipped','delivered','cancelled')),
    order_date TEXT NOT NULL
);
```

Seed with ~30–50 dummy products across a few categories, ~10 dummy customers, ~20 dummy orders in mixed statuses — enough variety to exercise every tool below.

### LLM tool/function definitions (this is what the LLM calls, never raw SQL)

Exposing fixed, parameterized tools instead of letting the LLM write raw SQL is a deliberate safety choice — it removes injection risk and keeps every query auditable.

| Tool | Args | Purpose |
|---|---|---|
| `search_products` | `query, category?, max_price?` | Find matching products |
| `get_product_details` | `product_id` | Full details on one product |
| `check_stock` | `product_id` | Stock level |
| `get_order_status` | `order_id` | Status of an order |
| `list_categories` | — | All available categories |
| `place_order` (dummy) | `customer_id, product_id, quantity` | Simulated order creation |

Each tool maps to one parameterized SQL statement — no string-built queries, ever.

---

## 6. Team Breakdown

### 🎙️ Team 1 — STT

**Owns:** everything from raw microphone audio to clean transcript text.

- [ ] Set up audio capture/upload endpoint; normalize to 16kHz mono PCM (`ffmpeg -i input.mp3 -ar 16000 -ac 1 output.wav` for anything that isn't already in that format)
- [ ] Add VAD (voice activity detection) to trim silence before inference
- [ ] Integrate IndicConformer via NeMo, wrapped in `BaseSTTProvider` exactly as shown in Section 3 — load the model once at startup (`nemo_asr.models.EncDecRNNTBPEModel.from_pretrained(...)`), never per-request
- [ ] Integrate SraVaani (`ARTPARK-IISc/SraVaani-1.0` on HuggingFace, via `transformers.AutoModel` with `trust_remote_code=True`) behind the same `BaseSTTProvider` interface as IndicConformer — pin an exact revision/commit hash in config rather than tracking `main` (see Section 8)
- [ ] Benchmark SraVaani against IndicConformer specifically on latency profile, not just WER — vendor guide reports ~2–5s/file on GPU and ~10–30s/file on CPU for SraVaani, a very different profile from IndicConformer's streaming-oriented ms-latency numbers; this affects which one makes sense as the default for real-time use
- [ ] Implement `BaseSTTProvider` + provider registry (Section 3)
- [ ] Expose `POST /stt/transcribe` per the Section 4 contract, built on FastAPI (equivalent to the "REST API" pattern in vendor examples, just consistent with the rest of our stack instead of Flask)
- [ ] Add a `/health` (or `/ready`) endpoint that reports "loading" until the model finishes initializing — model load takes ~3 minutes, and the gateway shouldn't route traffic to a service that isn't ready yet
- [ ] Benchmark: latency (p50/p95) and WER on Nepali test audio per model — use the vendor-reported **WER 26.9% (RNNT decoder)** and **50–180ms streaming latency** as a reference baseline, then re-measure on your own hardware/audio since these numbers are decoder-choice- and hardware-dependent
- [ ] Handle edge cases: silence, background noise, code-mixed Nepali/English speech
- [ ] Document GPU/CPU requirements per model — IndicConformer wants GPU for real-time use (~2GB VRAM per the vendor guide); CPU works for batch/offline transcription but is noticeably slower
- [ ] If containerizing: base the image on a NeMo-compatible container (e.g. `nvcr.io/nvidia/nemo:24.01.speech`) and pass the HF token in at **runtime** (`docker run -e HF_TOKEN=$HF_TOKEN ...`), never baked into the Dockerfile with `ENV HF_TOKEN=...` — that permanently embeds the secret in the image layers even after rotation
- [ ] (Stretch, Phase 7+) streaming/chunked transcription for partial results — WebSocket server accepting ~320ms audio chunks, per the vendor's real-time pattern; only take this on after the batch/REST path is solid

### 🧠 Team 2 — LLM + Database

**Owns:** transcript in → tool-augmented reasoning → reply text out.

- [ ] Build SQLite schema + seed script (Section 5)
- [ ] Write the 6 tool functions as parameterized queries (no raw SQL from the LLM)
- [ ] Define the tool-calling schema (JSON schema per tool) for whichever LLM provider is active
- [ ] Implement `BaseLLMProvider` + registry: Anthropic, OpenAI, and one local option (Ollama) at minimum
- [ ] Write the system prompt: role, tone, available tools, language behavior (reply in the same language the user spoke)
- [ ] Implement the tool-calling loop: LLM requests tool → orchestrator executes → result fed back → LLM drafts final reply
- [ ] Session/conversation memory (multi-turn, keyed by `session_id`)
- [ ] Expose `POST /llm/chat` per the Section 4 contract
- [ ] Log every tool call (name, args, result, latency) for debugging and eval
- [ ] Guardrails: read-only by default; `place_order` clearly marked dummy/simulated, no real side effects

### 🔊 Team 3 — TTS

**Owns:** reply text in → playable audio out.

- [ ] Integrate ElevenLabs API behind `BaseTTSProvider`
- [ ] Integrate Camb.ai API behind the same interface
- [ ] **Verify Nepali language/voice support on both providers before committing** — this is the single biggest risk in this stage (see Section 8); confirm via each provider's current docs, since coverage changes over time
- [ ] Implement fallback: if primary TTS provider errors, retry with secondary
- [ ] Handle audio format normalization (mp3 vs wav) for whatever the frontend/playback expects
- [ ] Expose `POST /tts/synthesize` per the Section 4 contract
- [ ] (Optional) cache TTS output for common/repeated phrases to cut latency and API cost
- [ ] Benchmark latency per provider, and voice-quality/naturalness for Nepali specifically

### 🔗 Shared / Integration (whoever leads overall)

- [ ] Freeze the Section 4 contracts before Week 1 ends
- [ ] Build the gateway/orchestrator that chains the 3 stages
- [ ] Own `config.yaml` schema and validate it on startup (fail fast on missing keys)
- [ ] End-to-end test harness: feed sample audio in, assert reasonable audio out
- [ ] Basic observability: per-session trace of `audio → text → tool calls → reply → audio` with timings at each hop

---

## 7. Suggested Repo Structure

```
voice-agent/
├── config/
│   └── config.yaml
├── services/
│   ├── stt_service/
│   │   ├── providers/ (base.py, indicconformer_provider.py, sravaani_provider.py)
│   │   ├── audio_utils.py
│   │   └── main.py
│   ├── llm_service/
│   │   ├── providers/ (base.py, anthropic_provider.py, openai_provider.py, ollama_provider.py)
│   │   ├── db/ (schema.sql, seed_data.py, db_manager.py)
│   │   ├── tools/ecommerce_tools.py
│   │   ├── orchestrator.py
│   │   └── main.py
│   └── tts_service/
│       ├── providers/ (base.py, elevenlabs_provider.py, camb_provider.py)
│       └── main.py
├── gateway/main.py
├── shared/schemas.py       # pydantic models used by all 3 teams — the Section 4 contract, in code
├── docker-compose.yml      # for the later microservice split
└── docs/architecture.md
```

---

## 8. Risks & Open Questions (flag these early, don't discover them in week 4)

1. **SraVaani requires `trust_remote_code=True`** — this executes Python code shipped inside the `ARTPARK-IISc/SraVaani-1.0` HuggingFace repo at load time, not just weights. That's normal for models with custom architectures, but it's a real supply-chain surface: pin an exact revision/commit hash in config (never track `main`), and don't bump the pinned revision without re-checking what changed. IndicConformer, loaded via NeMo's `from_pretrained`, doesn't carry this particular risk — worth knowing if you're choosing a default provider partly on that basis.
2. **Nepali support on ElevenLabs/Camb.ai TTS is not guaranteed** — check current voice/language coverage directly on their docs before committing engineering time; if neither supports Nepali well, options are: respond in transliterated/simplified form, use a multilingual voice model, or add a third open-source Nepali TTS provider behind the same interface.
3. **Latency stacking** — STT (local, GPU-bound) + LLM (network round-trip, possibly multiple tool-call turns) + TTS (network round-trip) can easily stack to several seconds. Decide early whether that's acceptable for MVP or whether streaming (partial STT results, streamed LLM tokens, streamed TTS) is needed — that's a bigger build, treat it as a later phase, not MVP.
4. **SQL safety** — never let the LLM generate free-form SQL; the fixed tool set in Section 5 is the guardrail. Keep it that way even under pressure to "just let it query anything."
5. **API keys / secrets** — all provider keys via env vars, never hardcoded, never committed. This includes the HuggingFace token used to pull the IndicConformer weights — if a token has ever been pasted into a doc, chat, or committed file, treat it as burned and rotate it at huggingface.co/settings/tokens before using it further.
6. **Language consistency** — if user speaks Nepali, the reply text and TTS output should stay Nepali (or a config-defined target language) — this should be explicit in the LLM system prompt, not assumed.
7. **Resolved — the checkpoint "mismatch" was misleading naming, not two different models.** `ai4bharat/indicconformer_stt_ne_hybrid_rnnt_large` (what's actually downloaded) and `ai4bharat/indicconformer_stt_ne_hybrid_ctc_rnnt_large` point to the same hybrid CTC+RNNT model — the shorter repo name just drops "ctc" from the name despite the model itself supporting both decoders. Load it with NeMo's `EncDecHybridRNNTCTCBPEModel`, then choose the decoder at runtime via `model.change_decoding_strategy(decoder_type="rnnt")`. Use RNNT for anything with a streaming path — it's the only one of the two that handles chunked/real-time input, CTC needs the full audio up front. CTC is a faster batch-only alternative worth comparing on accuracy for pure file-transcription workloads. The 26.9% WER benchmark figure in Team 1's targets was measured specifically with the RNNT decoder.
8. **Model load time** — IndicConformer takes roughly 3 minutes to load per the vendor's own guide. This affects service startup, container health checks, and any auto-scaling assumptions — build the readiness probe in Team 1's checklist so the gateway doesn't send requests to a service that's still loading.

---

## 9. Suggested Timeline

| Week | Milestone |
|---|---|
| 1 | Freeze interfaces (Section 4), repo scaffold, config schema, DB schema + seed data |
| 2–3 | Each team builds their stage independently against mocked inputs/outputs |
| 4 | Integration: wire STT → LLM → TTS through the gateway |
| 5 | End-to-end testing, latency benchmarking, provider comparisons |
| 6 | Fix rough edges (fallbacks, error handling, language consistency) |
| 7+ (stretch) | Streaming pipeline for lower perceived latency |

---

## 10. Tech Stack Summary

- **Language:** Python (FastAPI for each service)
- **STT:** NeMo toolkit (IndicConformer) + Hugging Face `transformers` (SraVaani, requires `trust_remote_code=True`), PyTorch, `soundfile`/`librosa` for audio I/O; container base image `nvcr.io/nvidia/nemo:24.01.speech` if containerizing IndicConformer, GPU + `nvidia-container-toolkit` required for real-time use
- **LLM:** provider-agnostic client layer (Anthropic/OpenAI SDKs, or Ollama for local)
- **DB:** SQLite (stdlib `sqlite3`, or SQLAlchemy for the query layer)
- **TTS:** ElevenLabs SDK/API, Camb.ai API
- **Config:** YAML + `pydantic-settings` for validation
- **Orchestration (later):** Docker Compose, one container per service
