# AI Agent Execution Platform

Decompose a complex task into subtasks, execute specialized agents, and return an
aggregated result. This repository is being built in phases; **Phase 1 (MVP) and
Phase 2 (distributed async execution) are complete.**

- **Backend:** Python + FastAPI + SQLAlchemy
- **Queue / workers:** Redis job queue + distributed worker processes (Phase 2)
- **Database:** SQLite by default (zero setup); Postgres for a production-style run
- **Frontend:** React (Vite)
- **LLM:** provider abstraction with a built-in **mock** provider (no API key needed),
  plus optional OpenAI / Anthropic providers

> Two execution modes: **`inline`** (Phase 1 — plan + run sequentially in-process,
> no Redis) and **`queue`** (Phase 2 — enqueue jobs to Redis; workers execute
> independent tasks concurrently). The Podman stack runs in `queue` mode. Later
> phases add retries/timeouts/SSE (Phase 3), tools + observability (Phase 4) and
> production polish (Phase 5). See [Roadmap](#roadmap).

---

## Architecture (Phase 2 — distributed)

```
   React UI ──REST/poll──▶ FastAPI ──enqueue "plan"──▶ ┌───────────────┐
      ▲                       │                        │  Redis queue  │
      │                       │                        └──────┬────────┘
      └────────poll───────────┘                    ┌──────────┼──────────┐
                                                    ▼          ▼          ▼
                                                 Worker     Worker     Worker
                                                    (claim task, run agent,
                                                     persist result, re-schedule)
                                        ┌───────────┴───────────┐
                                  Research   Analysis  (run concurrently)
                                        └───────────┬───────────┘
                                              Summarization  (joins / aggregates)
                                                    │
                                            PostgreSQL / SQLite
```

Flow: `POST /api/executions` creates an execution and enqueues a **plan** job. A
worker plans 2–5 subtasks with dependencies, then enqueues the **independent**
tasks. Multiple workers pull tasks concurrently, each claiming a task with an
atomic DB update, running its agent, persisting the result, and re-scheduling.
When every task is terminal, the aggregator produces the final answer. The UI
polls `GET /api/executions/{id}` for live progress.

**States**
- Execution: `PENDING → PLANNING → RUNNING → COMPLETED | FAILED`
- Task: `PENDING → RUNNING → COMPLETED | FAILED`

See [How parallel execution works](#how-parallel-execution-works) for the
dependency model and concurrency-safety details. The original in-process
sequential design (`inline` mode) is still available for a zero-dependency run.

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
│   │   ├── services/         # planner, executor, aggregator, orchestrator, scheduler
│   │   ├── jobqueue.py       # Redis job queue (Phase 2)
│   │   ├── worker.py         # distributed worker process (Phase 2)
│   │   ├── config.py         # env-driven settings
│   │   ├── database.py       # engine + session
│   │   └── main.py           # FastAPI app
│   ├── alembic/              # migrations (0001 schema, 0002 scheduling columns)
│   ├── requirements.txt
│   ├── Dockerfile
│   └── entrypoint.sh
├── frontend/                 # React + Vite app
├── docker-compose.yml        # db + redis + backend + worker + frontend
└── README.md
```

Clean separation of concerns: **API → services → agents → LLM**, with the
**database** and **schemas** layers kept independent.

---

## Prerequisites

- Python 3.9+ and Node 18+ for the native path, **or**
- Podman (or Docker) for the containerized path

---

## Quickstart A — Native, inline mode (no containers, no Redis)

Uses SQLite, the mock LLM, and in-process sequential execution — zero external
services.

**1) Backend**
```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# optional: cp .env.example .env   (defaults already work; EXECUTION_MODE=inline)
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

### Native queue mode (optional)
To run the distributed path natively you need a Redis server and at least one
worker. With Redis running on `localhost:6379`:
```bash
# terminal 1 — API in queue mode
cd backend && source .venv/bin/activate
EXECUTION_MODE=queue REDIS_URL=redis://localhost:6379/0 uvicorn app.main:app --port 8000

# terminal 2 — a worker (run more terminals / set WORKER_CONCURRENCY for parallelism)
cd backend && source .venv/bin/activate
EXECUTION_MODE=queue REDIS_URL=redis://localhost:6379/0 python -m app.worker
```
> Queue mode is best with Postgres. Concurrent writers on a single SQLite file
> can hit "database is locked"; use Postgres (or the Podman stack) for real
> concurrency.

---

## Quickstart B — Podman (Postgres + Redis + workers, queue mode)

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

This starts Postgres, Redis, the backend (migrations run automatically), a
**worker** (4 consumer threads by default), and the frontend in **queue mode**.
Open **http://localhost:5173**. Backend API: http://localhost:8000.

Run more worker processes for more parallelism:
```bash
podman compose up --build --scale worker=3
```

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
| `EXECUTION_MODE` | `inline` | `inline` (in-process) or `queue` (Redis + workers) |
| `REDIS_URL` | `redis://localhost:6379/0` | Redis connection (queue mode) |
| `WORKER_CONCURRENCY` | `4` | Consumer threads per worker process |
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
  subtasks, each tagged with an agent type, and assigns dependencies (see below).
  It parses defensively and falls back to a sensible default decomposition.
- **Agents** (`agents/`) — `research`, `analysis`, `summarization` — each wrap the
  LLM with a role-specific system prompt.
- **Scheduler** (`services/scheduler.py`, Phase 2) claims and runs a single task,
  then enqueues newly-unblocked dependents and finalizes the execution.
- **Executor** (`services/executor.py`) runs tasks in order for `inline` mode.
- **Aggregator** (`services/aggregator.py`) synthesizes the final result once all
  tasks are done (preferring the summarization output, with supporting work appended).
- **Job queue** (`jobqueue.py`) + **worker** (`worker.py`) provide the Redis queue
  and the multi-threaded consumer process for `queue` mode.
- **LLM abstraction** (`llm/`) keeps the app independent of any single provider;
  the default **mock** provider makes the whole pipeline run offline.

---

## How parallel execution works

**Dependency model (fan-out / fan-in).** The planner assigns each subtask a
`depends_on` list (indices of tasks that must finish first). By default,
research/analysis tasks are **independent** and a summarization task **depends on
all earlier tasks**:

```
research  ─┐
analysis  ─┴─▶ summarization        # research & analysis run concurrently
```

**Scheduling.** When an execution is created, a `plan` job is enqueued. A worker
plans the tasks and enqueues every task with no dependencies — these run
**concurrently** across workers/threads. As each task completes, the worker runs
a scheduling pass that enqueues any task whose dependencies are now all complete.
The **aggregator only runs once every task is terminal**.

**Concurrency-safety (no double work).** Correctness does not rely on the queue
(delivery is at-least-once). Every state transition is an **atomic, guarded
`UPDATE`**:

- *Claim a task:* `UPDATE tasks SET status='RUNNING' WHERE id=? AND status='PENDING'`.
  Only the worker whose update affects one row runs the task; duplicate deliveries
  are no-ops.
- *Enqueue once:* `UPDATE tasks SET enqueued=true WHERE id=? AND enqueued=false`
  ensures concurrent scheduling passes never enqueue the same task twice.
- *Finalize once:* `UPDATE executions SET status='COMPLETED' WHERE id=? AND
  status='RUNNING'` ensures a single worker finalizes/aggregates.

This is the classic compare-and-set pattern; Postgres `SELECT … FOR UPDATE SKIP
LOCKED` is an equivalent alternative. If a dependency fails, dependents are
cascaded to `FAILED` so the execution can finish deterministically.

**Scaling.** Increase `WORKER_CONCURRENCY` (threads per process) or run more
worker processes/containers (`--scale worker=N`). Because claims are atomic, any
number of workers is safe.

---

## Roadmap

- **Phase 1:** end-to-end MVP, sequential execution ✅
- **Phase 2:** Redis job queue + distributed workers, concurrent tasks, real-time UI ✅
- **Phase 3:** retries, exponential backoff, timeouts, idempotency, dead-letter queue, SSE
- **Phase 4:** agent tools (web search, calculator, fetch), observability + `/metrics`
- **Phase 5:** auth, rate limiting, health checks, CI, integration + load tests

Built and tested one phase at a time.
