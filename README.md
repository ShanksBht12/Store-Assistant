SQLite backend with a Groq-powered chatbot that answers **current
# edit .env and set GROQ_API_KEY (or set LLM_PROVIDER=mock to run without one)
asks Groq to phrase the answer. If no product matches,
# AI Business Agent — Phase 1

Phase 1 of the pluggable multimodal AI business agent: a FastAPI +
SQLite backend with a Grok-powered chatbot that answers **current
and historical price questions grounded in real database data**.

Later phases (see the full project spec) add tool calling, CRM,
HRM, omnichannel, multimodal input, guardrails, and event-driven
architecture — none of that is built yet, by design, so each phase
can be layered on cleanly.

## What works right now

- `GET /api/health` — health check
- `POST /api/chat` — chat with the agent, e.g. `"How much are A shoes?"`
- `GET /api/products/{id}` — look up a product
- `GET /api/products/{id}/price-history` — look up price history

The agent does a simple keyword match against the `products` table —
including product name **and color** ("black shoes", "pink shoes") —
builds a system prompt containing **only** real facts from the
database, and asks Grok to phrase the answer. If no product matches,
the LLM is told explicitly so it can't invent a price — this is the
anti-hallucination guarantee the full spec requires, implemented
from day one even before proper tool calling exists (Phase 2).

The matched product is also returned as structured data on the API
response (`product`), which the React frontend renders as a small
product card (image, color, price, stock) under the reply.

## Setup

```bash
cd ai-business-agent
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# edit .env and set GROK_API_KEY (or set LLM_PROVIDER=mock to run without one)

python -m app.database.seed   # creates app.db and seeds sample products
uvicorn app.main:app --reload
```

Visit `http://localhost:8000/docs` for interactive API docs.

## Try it

```bash
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "How much are A shoes?"}'

curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Were A shoes cheaper before?"}'
```

## Running without a Grok API key

Set `LLM_PROVIDER=mock` in `.env` — the `MockLLMProvider` returns a
deterministic response so you can verify the database-grounding logic
without any network calls or API costs.

## Frontend (React chat UI)

A Vite + React chat interface lives in `frontend/`. Run the backend
first (above), then in a second terminal:

```bash
cd frontend
npm install
cp .env.example .env
npm run dev
```

Open the printed URL (usually `http://localhost:5173`). Each agent
reply shows a **✓ FROM DATABASE** or **⚠ NO MATCH FOUND** stamp, and
a product card (image, color, price, stock) when a product was
matched — e.g. try "How much are black shoes?" or "Do you have pink
shoes?".

The backend's CORS config (`app/main.py`) allows `localhost:5173` by
default — update it before deploying anywhere public.

## Tests

```bash
pytest
```

Covers the two core demo scenarios: a grounded current-price answer,
and refusing to hallucinate when no product matches.

## Project structure

```text
ai-business-agent/
├── app/
│   ├── main.py                 # FastAPI app + router wiring
│   ├── config.py                # env-driven settings
│   ├── api/                     # HTTP routes (chat, products, health)
│   ├── agent/orchestrator.py    # Phase 1 grounding logic
│   ├── providers/llm/           # LLMProvider interface + grok/mock impls
│   ├── database/                # SQLAlchemy models, session, seed script
│   └── schemas/                 # Pydantic request/response models
├── frontend/                    # Vite + React chat UI
│   └── src/
│       ├── App.jsx              # chat UI, message list, product card
│       └── api.js               # calls the backend /api/chat endpoint
├── tests/
├── requirements.txt
└── .env.example
```

## Why this is already pluggable

`app/providers/llm/` defines an abstract `LLMProvider` with `GrokProvider`
and `MockLLMProvider` implementations, selected via the `LLM_PROVIDER`
env var through a small factory (`get_llm_provider()`). Nothing in
`app/agent/` or `app/api/` imports a concrete provider — only the
interface. The same pattern is what Phase 3–5 will reuse for
`CRMProvider`, `HRMProvider`, and `OmnichannelProvider`.

## Next steps (Phase 2)

- Add a `ToolRegistry` and let Grok call `get_current_price()` /
  `get_price_history()` as real function/tool calls instead of the
  current keyword-match + context-injection approach.
- Add `check_inventory()`, `search_products()` tools.
