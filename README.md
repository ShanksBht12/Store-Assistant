# AI Business Agent

A grounded e-commerce assistant built with FastAPI, SQLite, React, and Groq. It answers product questions using catalog data, returns the matching product and image, and keeps ambiguous follow-up questions within the product context already being discussed.

## Features

- Groq-powered chat through the OpenAI-compatible API
- Database-grounded product answers for price, stock, color, and history
- Product matching for shoes, backpacks, and color variants
- Context-aware follow-ups such as `What blue one?`
- Product cards with real images and expandable product details
- Full-image preview with description, price, stock, and SKU
- Casual conversation without unnecessary product cards
- Mock provider for offline development and tests
- FastAPI interactive documentation

## Stack

| Layer | Technology |
| --- | --- |
| Backend | FastAPI, Uvicorn, SQLAlchemy |
| Database | SQLite |
| LLM | Groq OpenAI-compatible Chat Completions API |
| Frontend | React, Vite |
| Testing | Pytest, pytest-asyncio |

## Project Structure

```text
ai-business-agent/
├── app/
│   ├── agent/              # Product matching and grounded responses
│   ├── api/                # Chat, health, and product routes
│   ├── database/           # SQLAlchemy models and seed data
│   ├── providers/llm/      # Groq and mock provider implementations
│   └── schemas/            # API request and response schemas
├── frontend/               # React and Vite chat application
├── tests/                  # Backend tests
├── .env.example            # Backend configuration template
└── requirements.txt        # Python dependencies
```

## Requirements

- Python 3.11 or newer
- Node.js 18 or newer
- A Groq API key from [Groq Console](https://console.groq.com/keys)

## Backend Setup

### Windows PowerShell

```powershell
cd D:\ai-business-agent
python -m venv venv
Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
```

Open `.env` and set:

```env
LLM_PROVIDER=groq
GROQ_API_KEY=your_groq_api_key
GROQ_API_BASE=https://api.groq.com/openai/v1
GROQ_MODEL=qwen/qwen3.6-27b
```

Seed the catalog and start the API:

```powershell
python -m app.database.seed
python -m uvicorn app.main:app --reload
```

The backend runs at `http://127.0.0.1:8000`.

### macOS or Linux

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python -m app.database.seed
python -m uvicorn app.main:app --reload
```

## Frontend Setup

In a second terminal:

```powershell
cd D:\ai-business-agent\frontend
npm install
Copy-Item .env.example .env
npm run dev
```

Open the URL printed by Vite, usually `http://localhost:5173`.

The frontend reads its backend URL from `VITE_API_BASE_URL`:

```env
VITE_API_BASE_URL=http://localhost:8000
```

## API

### Health Check

```http
GET /api/health
```

### Chat

```bash
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message":"How much are black shoes?"}'
```

The response includes the assistant reply and, when a product is matched, structured product data including its image URL.

### Product Endpoints

```http
GET /api/products/{product_id}
GET /api/products/{product_id}/price-history
```

Interactive API documentation is available at `http://localhost:8000/docs`.

## Example Questions

- `How much are black shoes?`
- `Do you have pink shoes?`
- `Show me the blue backpack`
- `What blue one?` after discussing a product
- `Were these shoes cheaper before?`
- `Hi`

Product questions are answered from the catalog. Casual messages are handled as conversation without showing a product card. If a requested variant does not exist, the assistant does not invent product information.

## Testing

Run the backend tests from the repository root:

```powershell
.\venv\Scripts\python.exe -m pytest
```

Run a production build for the frontend:

```powershell
cd frontend
npm run build
```

## Offline Development

To run without a Groq API request, set this in `.env`:

```env
LLM_PROVIDER=mock
```

The mock provider returns deterministic responses for local testing. Database matching and API behavior can be tested without network access or usage costs.

## Configuration

| Variable | Purpose | Default |
| --- | --- | --- |
| `LLM_PROVIDER` | Selects `groq` or `mock` | `groq` |
| `GROQ_API_KEY` | Groq authentication key | Empty |
| `GROQ_API_BASE` | Groq API base URL | `https://api.groq.com/openai/v1` |
| `GROQ_MODEL` | Groq chat model | `qwen/qwen3.6-27b` |
| `DATABASE_URL` | SQLAlchemy database URL | `sqlite:///./app.db` |
| `MAX_INPUT_TOKENS` | Input guardrail setting | `4000` |
| `MAX_OUTPUT_TOKENS` | Output token limit | `1000` |

## Security Notes

- Keep `.env` local and never commit API keys.
- Use `.env.example` as the shareable configuration template.
- Rotate any key that has been exposed in source code, logs, screenshots, or chat messages.
- Tighten the CORS origins in `app/main.py` before public deployment.

## Roadmap

- Replace keyword matching with a tool registry and structured product tools.
- Add inventory, order, CRM, and customer-service workflows.
- Add database migrations with Alembic.
- Add production deployment configuration and observability.
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
