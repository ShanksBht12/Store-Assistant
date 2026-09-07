# Store Assistant — AI Business Agent

A conversational AI sales assistant for a fashion and lifestyle store, built with FastAPI, SQLAlchemy, DSPy, React, and OpenRouter. Customers can browse products, place orders, and track deliveries through a natural chat interface. Store owners get an admin API to manage orders, update store information, and version the AI system prompt.

## Features

### Chat & AI
- Real LLM function/tool calling — the agent decides which tools to invoke per turn
- Full conversation memory persisted per session in SQLite (`ConversationState`)
- Remembers customer names, previous products, and context across messages
- DSPy architecture (`ChatSignature`, `SalesAgentModule`) with per-request `dspy.context()` for async-safe model switching
- Markdown stripped from all replies — clean plain-text responses
- Suggestion chips on the welcome screen for quick-start prompts

### Dynamic Store Information
- All store facts (name, location, phone, email, Instagram, opening hours, return/exchange/delivery policies, festive sale details) are stored in the database — not hardcoded anywhere
- `GET /api/store` returns the current store info; `PUT /api/store` updates any field instantly
- Agent calls the `get_store_info` tool whenever a customer asks about the store — answers always reflect the live database values
- Change any store detail via the API and the chatbot picks it up on the very next message, no restart needed

### Products
- Search by keyword, brand, color, or category
- Comparative queries ("cheapest", "most expensive") across the full catalog
- Price history lookup per product
- Live stock check before any order is placed
- Product cards with image, price, stock, and brand — click to expand full detail modal

### Orders
- Full guided checkout: product → size/color → name → phone → address → payment
- Nepali mobile number validation (98/97/96 prefix, 10 digits)
- Stock decremented atomically in the same transaction as the order
- eSewa and Khalti QR codes rendered automatically after digital payment orders
- Cash on Delivery supported
- Order status lookup by order ID or phone number

### Prompt Versioning
- Every system prompt change is saved as a new row in `prompt_versions`
- `GET /api/prompts`, `POST /api/prompts`, `POST /api/prompts/{id}/activate`
- Activating a new prompt version takes effect on the next request — no restart needed
- Designed for DSPy `BootstrapFewShot` optimization: save optimized prompts as new versions via the API

### Admin
- `GET /api/orders` — paginated list with filters: status, name/phone search, date range
- `GET /api/orders/{id}` — single order detail
- `PATCH /api/orders/{id}/status` — mark as paid or cancelled (restores stock on cancel)
- `GET /api/store` / `PUT /api/store` — read and update store information
- `GET /api/prompts` / `POST /api/prompts` — manage system prompt versions
- Interactive API docs at `http://localhost:8000/docs`

### Frontend
- Modern dark SaaS chat UI with Inter font
- Sidebar with capability list and new conversation button
- Auto-resizing textarea, Enter to send, Shift+Enter for newlines
- Character counter with colour warnings
- Agent avatar and per-message timestamps
- Toast notifications for order confirmations and errors
- Full product image modal with details and buy button
- QR payment modal — click the QR thumbnail to zoom to full card
- Fully responsive — sidebar hides on mobile

## Stack

| Layer | Technology |
|---|---|
| Backend | FastAPI, Uvicorn, SQLAlchemy |
| AI Framework | DSPy (signatures, modules, per-request context) |
| Database | SQLite (`app.db`) |
| LLM | OpenRouter (default) · OpenAI · Groq · Mock |
| Frontend | React 18, Vite |

## Project Structure

```
ai-business-agent/
├── app/
│   ├── agent/
│   │   ├── agent.py          # Tool-calling loop + conversation memory
│   │   ├── prompt.py         # DSPy ChatSignature, SalesAgentModule, PromptRegistry, SYSTEM_PROMPT
│   │   ├── router.py         # Model selection, dspy.context() per request
│   │   └── tools.py          # Tool registry: search, stock, order, store info, best sellers, etc.
│   ├── api/
│   │   ├── chat.py           # POST /api/chat
│   │   ├── orders.py         # GET|PATCH /api/orders admin endpoints
│   │   ├── prompts.py        # GET|POST /api/prompts prompt versioning
│   │   └── store.py          # GET|PUT /api/store store information
│   ├── database/
│   │   ├── database.py       # SQLAlchemy engine and session
│   │   ├── models.py         # Product, Order, ConversationState, PriceHistory, PromptVersion, StoreInfo
│   │   └── seed.py           # Product catalog seed + seed_store_info()
│   ├── providers/llm/
│   │   ├── base.py           # Abstract LLMProvider interface
│   │   ├── openai_provider.py # OpenAI / OpenRouter
│   │   ├── groq.py           # Groq
│   │   ├── generic.py        # Generic OpenAI-compatible endpoint
│   │   └── mock.py           # Offline mock for local dev
│   ├── schemas/
│   │   ├── chat.py           # ChatRequest / ChatResponse
│   │   ├── order.py          # OrderOut / OrderListResponse
│   │   ├── product.py        # ProductOut / PriceHistoryOut
│   │   ├── prompt.py         # PromptVersionOut / PromptVersionCreate
│   │   └── store.py          # StoreInfoOut / StoreInfoUpdate
│   ├── config.py             # Settings loaded from .env
│   └── main.py               # FastAPI app, CORS, router registration, startup seeds
├── frontend/
│   ├── src/
│   │   ├── App.jsx           # Chat UI, all components
│   │   ├── api.js            # sendMessage() fetch wrapper
│   │   ├── index.css         # Design system and all styles
│   │   └── assets/           # eSewa and Khalti QR PNG cards
│   └── index.html
├── app.db                    # SQLite database (auto-created on first run)
├── .env                      # Local secrets — never commit
├── .env.example              # Configuration template
└── requirements.txt
```

## Requirements

- Python 3.11+
- Node.js 18+
- An OpenRouter API key — free tier available at [openrouter.ai](https://openrouter.ai)

## Setup

### 1. Backend

```powershell
# Windows PowerShell
cd D:\ai-business-agent
python -m venv venv
Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
```

Open `.env` and set your key:

```env
LLM_PROVIDER=openai
OPENAI_API_KEY=sk-or-v1-your-openrouter-key
OPENAI_API_BASE=https://openrouter.ai/api/v1
OPENAI_MODEL=openai/gpt-4o-mini
```

Start the API:

```powershell
python -m app.database.seed
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

The backend runs at `http://localhost:8000`. Interactive docs at `http://localhost:8000/docs`.

The server automatically seeds the product catalog, store information, and initial prompt version on first startup — no manual DB step needed after the first `seed` run.

### 2. Frontend

In a second terminal:

```powershell
cd D:\ai-business-agent\frontend
npm install
npm run dev
```

Open the URL printed by Vite — usually `http://localhost:5174`.

### macOS / Linux

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# edit .env, then:
python -m app.database.seed
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

## Configuration

| Variable | Purpose | Default |
|---|---|---|
| `LLM_PROVIDER` | `openai` · `groq` · `mock` | `openai` |
| `OPENAI_API_KEY` | OpenRouter or OpenAI key | — |
| `OPENAI_API_BASE` | API base URL | `https://openrouter.ai/api/v1` |
| `OPENAI_MODEL` | Model name | `openai/gpt-4o-mini` |
| `GROQ_API_KEY` | Groq key (if using Groq) | — |
| `GROQ_MODEL` | Groq model | `qwen/qwen3.6-27b` |
| `DATABASE_URL` | SQLAlchemy URL | `sqlite:///./app.db` |
| `MAX_INPUT_TOKENS` | Input token limit | `4000` |
| `MAX_OUTPUT_TOKENS` | Output token limit | `2000` |
| `DEBUG` | FastAPI debug mode | `true` |

## API Reference

### Chat

```http
POST /api/chat
Content-Type: application/json

{ "message": "Where is the store?", "conversation_id": "optional-uuid" }
```

Response:
```json
{
  "conversation_id": "uuid",
  "reply": "We're located at Durbar Marg, Kathmandu. Open Sunday to Friday, 10 AM to 7 PM.",
  "product": null,
  "payment_method": null
}
```

`conversation_id` is generated on the first turn and must be echoed back on every subsequent message to maintain memory.

`payment_method` is `"esewa"` or `"khalti"` when an order is confirmed with a digital payment — the frontend uses this to render the QR card.

### Store Info

```http
GET /api/store
PUT /api/store
Content-Type: application/json

{
  "store_name": "Style Store",
  "location": "Durbar Marg, Kathmandu",
  "phone": "9800000006",
  "email": "stylestore@gmail.com",
  "instagram": "@stylestore",
  "opening_hours": "Sunday to Friday, 10:00 AM to 7:00 PM.",
  "return_policy": "...",
  "exchange_policy": "...",
  "delivery_info": "...",
  "extra_notes": "..."
}
```

All `PUT` fields are optional — only the supplied fields are updated. Changes are reflected in chatbot responses immediately.

### Orders (Admin)

```http
GET  /api/orders?status=pending_payment&search=john&page=1&page_size=20
GET  /api/orders/{id}
PATCH /api/orders/{id}/status?status=paid
```

### Prompts (Admin)

```http
GET  /api/prompts
POST /api/prompts          { "prompt_text": "...", "label": "v2", "activate": true }
POST /api/prompts/{id}/activate
```

Full schema and try-it-out available at `/docs`.

## Updating Store Information

To change any store detail without touching the code:

```powershell
# Example: update phone number and location
$body = '{"phone": "9812345678", "location": "Thamel, Kathmandu"}'
Invoke-RestMethod -Uri "http://localhost:8000/api/store" -Method PUT -Body $body -ContentType "application/json"
```

The chatbot will use the new values on the very next customer message.

## Payment QR Codes

After a successful eSewa or Khalti order the frontend automatically renders a payment QR card. Clicking the thumbnail opens a full-size zoom modal.

To use your real merchant IDs, update the `merchantId` values in `QR_CONFIG` at the top of `frontend/src/App.jsx`, and replace the PNG files in `frontend/src/assets/` with QR images downloaded from your eSewa/Khalti merchant dashboard.

## Offline Development

Set `LLM_PROVIDER=mock` in `.env` to run without any API key. The mock provider returns deterministic responses so you can test the full request/response pipeline locally.

## Security Notes

- Never commit `.env` — it is listed in `.gitignore`.
- Use `.env.example` as the shareable template.
- Rotate any key that has appeared in source, logs, or screenshots.
- Before deploying publicly, restrict the CORS `allow_origin_regex` in `app/main.py` to your actual frontend domain.
- The admin order and store endpoints have no authentication — add an API key or session check before exposing them outside localhost.
