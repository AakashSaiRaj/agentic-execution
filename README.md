# AI Agent Execution Platform

Decompose a complex task into subtasks, execute specialized agents, and return an
aggregated result. This repository is being built in phases; **this is Phase 1: a
working end-to-end MVP.**

- **Backend:** Python + FastAPI + SQLAlchemy
- **Database:** SQLite by default (zero setup); Postgres for a production-style run
- **Frontend:** React (Vite)
- **LLM:** provider abstraction with a built-in **mock** provider (no API key needed),
  plus optional OpenAI / Anthropic providers

> Phase 1 executes subtasks **sequentially, in-process**. Later phases add a Redis
> job queue and distributed workers (Phase 2), retries/timeouts/SSE (Phase 3),
> tools + observability (Phase 4) and production polish (Phase 5). See
> [Roadmap](#roadmap).

---

## Architecture (Phase 1)

```
   React UI  ──REST/poll──▶  FastAPI  ──▶  Orchestrator ──▶ Planner (LLM)
      ▲                        │                │
      │                        │                ▼
      └────────poll────────────┘        Sequential Executor
                                                │
                                  Research ▶ Analysis ▶ Summarization  (agents)
                                                │
                                           Aggregator
                                                │
                                        SQLite / Postgres
```

Flow: `POST /api/executions` creates an execution and returns immediately. A
background task plans 2–5 subtasks, runs each agent in order (feeding earlier
outputs forward as context), stores every result, then aggregates a final answer.
The UI polls `GET /api/executions/{id}` to show live status.

**States**
- Execution: `PENDING → PLANNING → RUNNING → COMPLETED | FAILED`
- Task: `PENDING → RUNNING → COMPLETED | FAILED`

---

## Project structure

```
.
├── backend/
│   ├── app/
│   │   ├── api/routes/       # executions + health endpoints
│   │   ├── agents/           # research, analysis, summarization + registry
│   │   ├── llm/              # provider abstraction: base, mock, openai, anthropic
│   │   ├── models/           # SQLAlchemy models (execution, task, task_result)
│   │   ├── schemas/          # Pydantic request/response models
│   │   ├── services/         # planner, executor, aggregator, orchestrator
│   │   ├── config.py         # env-driven settings
│   │   ├── database.py       # engine + session
│   │   └── main.py           # FastAPI app
│   ├── alembic/              # migrations
│   ├── requirements.txt
│   ├── Dockerfile
│   └── entrypoint.sh
├── frontend/                 # React + Vite app
├── docker-compose.yml        # db + backend + frontend (Podman/Docker)
└── README.md
```

Clean separation of concerns: **API → services → agents → LLM**, with the
**database** and **schemas** layers kept independent.

---

## Prerequisites

- Python 3.9+ and Node 18+ for the native path, **or**
- Podman (or Docker) for the containerized path

---

## Quickstart A — Native (no containers)

Uses SQLite and the mock LLM, so it runs with zero external services.

**1) Backend**
```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# optional: cp .env.example .env   (defaults already work)
alembic upgrade head
uvicorn app.main:app --reload --port 8000
```
Backend is now at http://localhost:8000 (interactive docs at `/docs`).

**2) Frontend** (in a second terminal)
```bash
cd frontend
npm install
npm run dev
```
Open **http://localhost:5173**. The Vite dev server proxies `/api` to the backend.

---

## Quickstart B — Podman (Postgres + full stack)

On macOS, start the Podman VM once:
```bash
podman machine init   # first time only
podman machine start
```

Then from the repo root:
```bash
podman compose up --build
# (equivalent: podman-compose up --build)
```

This starts Postgres, the backend (migrations run automatically on startup) and
the frontend. Open **http://localhost:5173**. Backend API: http://localhost:8000.

Stop with `Ctrl-C`, then `podman compose down` (add `-v` to also drop the DB volume).

---

## Configuration

All configuration is via environment variables (see `backend/.env.example` and
`.env.example`).

| Variable | Default | Description |
|---|---|---|
| `DATABASE_URL` | `sqlite:///./app.db` | SQLAlchemy URL. Postgres: `postgresql+psycopg2://user:pass@host:5432/db` |
| `LLM_PROVIDER` | `mock` | `mock`, `openai`, or `anthropic` |
| `LLM_MODEL` | `mock-model` | Model name for the chosen provider |
| `LLM_TEMPERATURE` | `0.2` | Sampling temperature |
| `LLM_MAX_TOKENS` | `1024` | Max output tokens |
| `PLANNER_MIN_TASKS` / `PLANNER_MAX_TASKS` | `2` / `5` | Subtask count bounds |
| `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` | — | Required only for real providers |
| `LOG_LEVEL` | `INFO` | Logging level |
| `CORS_ORIGINS` | `*` | Comma-separated origins, or `*` |

### Using a real LLM
The provider is swappable without code changes. Install the SDK and set env vars:
```bash
pip install "openai>=1.0"        # or: pip install "anthropic>=0.39"
export LLM_PROVIDER=openai
export LLM_MODEL=gpt-4o-mini
export OPENAI_API_KEY=sk-...
```

---

## API

Base URL: `http://localhost:8000` (paths are under `/api`).

**Create an execution**
```bash
curl -X POST http://localhost:8000/api/executions \
  -H 'Content-Type: application/json' \
  -d '{"user_request": "Compare REST and gRPC for an internal microservice."}'
```

**Get an execution (status, subtasks, results, final answer)**
```bash
curl http://localhost:8000/api/executions/<execution_id>
```

**List an execution's tasks**
```bash
curl http://localhost:8000/api/executions/<execution_id>/tasks
```

**List recent executions**
```bash
curl http://localhost:8000/api/executions
```

**Health**
```bash
curl http://localhost:8000/health
```

---

## How it works

- **Planner** (`services/planner.py`) prompts the LLM for a JSON list of 2–5
  subtasks, each tagged with an agent type. It parses defensively and falls back
  to a sensible default decomposition if the model returns something unusable.
- **Agents** (`agents/`) — `research`, `analysis`, `summarization` — each wrap the
  LLM with a role-specific system prompt.
- **Sequential executor** (`services/executor.py`) runs tasks in order, updating
  `PENDING → RUNNING → COMPLETED/FAILED` and passing earlier outputs forward as
  context. It stops at the first failure.
- **Aggregator** (`services/aggregator.py`) synthesizes the final result
  (preferring the summarization output, with supporting work appended).
- **LLM abstraction** (`llm/`) keeps the app independent of any single provider;
  the default **mock** provider makes the whole pipeline run offline.

---

## Roadmap

- **Phase 1 (this repo):** end-to-end MVP, sequential execution ✅
- **Phase 2:** Redis job queue + distributed workers, concurrent tasks, real-time UI
- **Phase 3:** retries, exponential backoff, timeouts, idempotency, dead-letter queue, SSE
- **Phase 4:** agent tools (web search, calculator, fetch), observability + `/metrics`
- **Phase 5:** auth, rate limiting, health checks, CI, integration + load tests

Built and tested one phase at a time — get Phase 1 working before moving on.
