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
