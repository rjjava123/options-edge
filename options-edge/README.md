# Options Edge

AI-powered options trading analysis platform. Combines quantitative screening, technical pattern recognition, and LLM-driven synthesis (Claude) to produce actionable spread trade theses with a built-in feedback loop.

## Stack

- **Backend**: Python 3.12, FastAPI, LangGraph, SQLAlchemy (async), PostgreSQL
- **Frontend**: Next.js 14, TypeScript, Tailwind CSS
- **LLM**: Claude (Anthropic API) with web search
- **Data**: Polygon (Massive) + Benzinga free tier

## Quick Start (Local Dev)

### 1. Prerequisites
- Docker Desktop
- Node.js 18+
- Python 3.12+

### 2. Backend

```bash
cd backend
cp .env.example .env
# Fill in your API keys in .env

# Start Postgres + backend via Docker
docker compose up -d db
pip install -r requirements.txt
uvicorn app.main:app --reload
```

API docs: http://localhost:8000/docs

### 3. Run Migrations

```bash
cd backend
alembic upgrade head
```

### 4. Frontend

```bash
cd frontend
npm install
npm run dev
```

UI: http://localhost:3000

### 5. Full Stack (Docker)

```bash
docker compose up --build
```

## Project Structure

```
options-edge/
├── backend/
│   ├── app/
│   │   ├── main.py           # FastAPI entry point
│   │   ├── config.py         # Settings / API keys
│   │   ├── models/           # SQLAlchemy ORM + Pydantic schemas
│   │   ├── graph/            # LangGraph nodes + builder
│   │   ├── screener/         # Quantitative screener pipeline
│   │   ├── technicals/       # Technical indicator calculations
│   │   ├── data/             # Polygon + Benzinga API clients
│   │   ├── tracking/         # P&L snapshots + exit logic
│   │   ├── alerts/           # Gmail API email alerts
│   │   ├── db/               # Database setup + repositories
│   │   └── api/              # FastAPI routes
│   └── jobs/                 # Scheduled job runners
└── frontend/
    └── src/
        ├── app/              # Next.js app router pages
        ├── components/       # Shared UI components
        └── lib/              # API client
```

## Flows

1. **Discovery** — Automated pre-market + midday screener (3000-4000 tickers → 30-80 candidates → LLM analysis → email)
2. **Validation** — On-demand single-ticker deep analysis
3. **Watchlist & News** — Persistent watchlist with AI-synthesized news
4. **Thesis Tracking** — Daily P&L snapshots, exit condition monitoring, email alerts
5. **Scoring Dashboard** — Historical thesis review + trap detection

## Environment Variables

See `backend/.env.example` for all required keys:
- `ANTHROPIC_API_KEY`
- `POLYGON_API_KEY`
- `BENZINGA_API_KEY`
- `DATABASE_URL`
- `GMAIL_*` credentials
