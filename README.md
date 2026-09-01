# Store Assistant — AI Business Agent

A conversational AI sales assistant for a shoe store, built with FastAPI, SQLAlchemy, React, and OpenRouter. Customers can browse products, place orders, and track deliveries through a natural chat interface. Store owners get an admin API to manage orders.

## Features

### Chat & AI
- Real LLM function/tool calling — the agent decides which tools to invoke per turn
- Full conversation memory persisted per session in SQLite (`ConversationState`)
- Remembers customer names, previous products, and context across messages
- Suggestion chips on the welcome screen for quick-start prompts
- Markdown stripped from all replies — clean plain-text responses

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

### Admin
- `GET /api/orders` — paginated list with filters: status, name/phone search, date range
- `GET /api/orders/{id}` — single order detail
- `PATCH /api/orders/{id}/status` — mark as paid or cancelled (restores stock on cancel)
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
| Database | SQLite (`app.db`) |
| LLM | OpenRouter (default) · OpenAI · Groq · Mock |
| Frontend | React 18, Vite |

## Project Structure

```
ai-business-agent/
├── app/
│   ├── agent/
│   │   ├── agent.py          # Phase 2 tool-calling loop + conversation memory
│   │   └── tools.py          # Tool registry: search, stock, price history, order, status
│   ├── api/
│   │   ├── chat.py           # POST /api/chat
│   │   └── orders.py         # GET|PATCH /api/orders admin endpoints
│   ├── database/
│   │   ├── database.py       # SQLAlchemy engine and session
│   │   └── models.py         # Product, Order, ConversationState, PriceHistory
│   ├── providers/llm/
│   │   ├── base.py           # Abstract LLMProvider interface
│   │   ├── openai_provider.py # OpenAI / OpenRouter
│   │   ├── groq.py           # Groq
│   │   └── mock.py           # Offline mock for local dev
│   ├── schemas/
│   │   ├── chat.py           # ChatRequest / ChatResponse
│   │   ├── order.py          # OrderOut / OrderListResponse
│   │   └── product.py        # ProductOut / PriceHistoryOut
│   ├── config.py             # Settings loaded from .env
│   └── main.py               # FastAPI app, CORS, router registration
├── frontend/
│   ├── src/
│   │   ├── App.jsx           # Chat UI, all components
│   │   ├── api.js            # sendMessage() fetch wrapper
│   │   ├── index.css         # Design system and all styles
│   │   └── assets/           # eSewa and Khalti QR PNG cards
│   └── index.html
├── app.db                    # SQLite database (products + orders + conversations)
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
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

The backend runs at `http://localhost:8000`. Interactive docs at `http://localhost:8000/docs`.

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

{ "message": "How much are black shoes?", "conversation_id": "optional-uuid" }
```

Response:
```json
{
  "conversation_id": "uuid",
  "reply": "The Nike Air Max in Black is 13,000 NPR and we have 20 in stock.",
  "product": { "id": 8, "name": "Nike Air Max", "color": "Black", ... },
  "payment_method": null
}
```

`conversation_id` is generated on the first turn and must be echoed back on every subsequent message to maintain memory.

`payment_method` is `"esewa"` or `"khalti"` when an order is confirmed with a digital payment — the frontend uses this to render the QR card.

### Orders (Admin)

```http
GET  /api/orders?status=pending_payment&search=sandeep&page=1&page_size=20
GET  /api/orders/{id}
PATCH /api/orders/{id}/status?status=paid
```

Full schema and try-it-out available at `/docs`.

## Payment QR Codes

After a successful eSewa or Khalti order the frontend automatically renders a payment QR card matching your reference design (dark background, provider logo, store name, merchant number, scan hint). Clicking the thumbnail opens a full-size zoom modal.

To use your real merchant IDs, update the `merchantId` values in `QR_CONFIG` at the top of `frontend/src/App.jsx`, and replace the PNG files in `frontend/src/assets/` with QR images downloaded from your eSewa/Khalti merchant dashboard.

## Offline Development

Set `LLM_PROVIDER=mock` in `.env` to run without any API key. The mock provider returns deterministic responses so you can test the full request/response pipeline locally.

## Security Notes

- Never commit `.env` — it is listed in `.gitignore`.
- Use `.env.example` as the shareable template.
- Rotate any key that has appeared in source, logs, or screenshots.
- Before deploying publicly, restrict the CORS `allow_origin_regex` in `app/main.py` to your actual frontend domain.
- The admin order endpoints have no authentication — add an API key or session check before exposing them outside localhost.
