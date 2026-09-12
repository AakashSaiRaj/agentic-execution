# AI Agent Execution Platform

A distributed platform that decomposes a complex task into subtasks, executes
specialized agents (with tools) through an asynchronous worker system, and
streams execution progress and results to the user. **Feature-complete
(Phases 1–5).**

- **Backend:** Python + FastAPI + SQLAlchemy
- **Queue / workers:** Redis job queue + distributed worker processes
- **Reliability:** retries w/ exponential backoff, timeouts, idempotency,
  dead-letter queue, crash recovery
- **Real-time:** Server-Sent Events stream to the UI (no polling)
- **Tools:** agents invoke registered tools (calculator, web search, URL fetch)
  via structured tool calling
- **Observability:** execution/task durations, token usage, estimated cost,
  tool-call counts, structured logs, and a `/metrics` endpoint
- **Production:** API-key auth, rate limiting, request limits, health checks,
  graceful shutdown, DB indexes, prod Docker config, and a GitHub Actions CI
  pipeline (lint + unit + integration)
- **Database:** SQLite by default (zero setup); Postgres for a production-style run
- **Frontend:** React (Vite)
- **LLM:** provider abstraction with a built-in **mock** provider (no API key needed),
  plus optional OpenAI / Anthropic providers

> Two execution modes: **`inline`** (Phase 1 — plan + run sequentially in-process,
> no Redis) and **`queue`** (Phase 2 — enqueue jobs to Redis; workers execute
> independent tasks concurrently). The Podman stack runs in `queue` mode. Later
> phases add tools + observability (Phase 4) and production polish (Phase 5). See
> [Roadmap](#roadmap) and [Failure handling](#failure-handling--reliability-phase-3).

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
│   │   ├── api/              # routes + security (auth) 
│   │   ├── services/         # planner, executor, aggregator, orchestrator, scheduler
│   │   ├── tools/            # tool registry + calculator / web_search / fetch_url
│   │   ├── observability/    # DB-derived metrics collector
│   │   ├── middleware.py     # rate limiting + request-size limits (Phase 5)
│   │   ├── jobqueue.py       # Redis job queue
│   │   ├── worker.py         # distributed worker process
│   │   ├── config.py         # env-driven settings
│   │   ├── database.py       # engine + session
│   │   └── main.py           # FastAPI app
│   ├── alembic/              # migrations (0001..0005)
│   ├── tests/                # pytest (reliability, tools, integration)
│   ├── pyproject.toml        # ruff + pytest config
│   ├── requirements.txt
│   ├── Dockerfile
│   └── entrypoint.sh
├── frontend/                 # React + Vite app (+ Dockerfile.prod, nginx.conf)
├── scripts/loadtest.py       # basic load test
├── .github/workflows/ci.yml  # lint + unit + integration
├── docker-compose.yml        # dev stack (db + redis + backend + worker + frontend)
├── docker-compose.prod.yml   # production stack (nginx frontend, auth, workers)
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
| `TASK_MAX_RETRIES` | `3` | Retries after the first attempt (total tries = N+1) |
| `TASK_TIMEOUT_SECONDS` | `30` | Hard timeout per task execution |
| `RETRY_BACKOFF_BASE_SECONDS` / `RETRY_BACKOFF_MAX_SECONDS` | `1` / `30` | Exponential backoff bounds |
| `RETRY_BACKOFF_JITTER` | `true` | Add ±20% jitter to backoff |
| `TASK_LEASE_SECONDS` | `90` | RUNNING lease; longer-stuck tasks are recovered |
| `TOOLS_ENABLED` | `true` | Enable agent tool calling |
| `TOOL_TIMEOUT_SECONDS` | `10` | Per-tool execution timeout |
| `AGENT_MAX_TOOL_ITERATIONS` | `3` | Max tool-call rounds per agent |
| `FETCH_MAX_BYTES` | `20000` | Truncation cap for the fetch_url tool |
| `API_KEY` / `API_KEYS` | — | API key(s). If unset, **auth is disabled** (dev). Set in prod. |
| `RATE_LIMIT_PER_MINUTE` | `0` | Requests/min per client (0 = disabled) |
| `MAX_REQUEST_BYTES` | `65536` | Reject larger request bodies (413) |
| `UVICORN_WORKERS` | `1` | API worker processes (prod) |
| `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` | — | Required only for real providers |
| `LOG_LEVEL` | `INFO` | Logging level |
| `LOG_FORMAT` | `text` | `text` or `json` (structured logs) |
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

> **Auth:** when `API_KEY` is set, send it as `X-API-Key: <key>` (or
> `Authorization: Bearer <key>`, or `?api_key=<key>` for SSE). With no key
> configured, auth is disabled. `/health` and `/metrics` stay open.

**Create an execution**
```bash
curl -X POST http://localhost:8000/api/executions \
  -H 'Content-Type: application/json' \
  -d '{"user_request": "Compare REST and gRPC for an internal microservice."}'
# with auth enabled, add:  -H 'X-API-Key: <your-key>'
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

**Stream live updates (SSE — no polling)**
```bash
curl -N http://localhost:8000/api/executions/<execution_id>/events
```

**Dead-letter queue (permanently-failed jobs)**
```bash
curl http://localhost:8000/api/dead-letter
```

**Metrics** (JSON for the UI, Prometheus text for scrapers)
```bash
curl http://localhost:8000/api/metrics
curl http://localhost:8000/metrics
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
- **Scheduler** (`services/scheduler.py`) claims and runs a single task (with a
  timeout), persists its result idempotently, retries with backoff or dead-letters
  on exhaustion, enqueues newly-unblocked dependents, and finalizes the execution.
  Its reaper recovers tasks from crashed workers.
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

## Failure handling & reliability (Phase 3)

Distributed work fails in messy ways — a model call errors, a request hangs, a
worker crashes mid-task, or the same job is delivered twice. Phase 3 makes the
platform tolerate all of these.

**Retries with exponential backoff.** A failed task is retried up to
`TASK_MAX_RETRIES` times. Between attempts it waits
`base * 2^(attempt-1)` seconds (capped, with jitter), so a flaky dependency isn't
hammered. *Why:* transient failures (timeouts, rate limits, blips) are common and
usually succeed on retry; backoff prevents retry storms.

**Timeouts.** Each task runs under a hard `TASK_TIMEOUT_SECONDS` limit. A hung
call is abandoned and treated as a failure (then retried). *Why:* without a
timeout, one stuck request pins a worker forever and the execution never
finishes.

**Idempotency.** `task_results.task_id` is `UNIQUE`, so a task can produce **at
most one** result no matter how many times it is retried or double-delivered.
Before running, a worker also short-circuits if a result already exists. *Why:*
at-least-once delivery + retries mean the same task can run more than once;
idempotency keeps that from creating duplicate or conflicting output.

**Dead-letter queue.** When retries are exhausted the task is marked `FAILED` and
a record is pushed to a Redis dead-letter list (`GET /api/dead-letter`). *Why:*
permanently-failed work should be visible and inspectable, not silently dropped.

**Crash recovery (lease/heartbeat).** Claiming a task stamps `updated_at`. A
reaper thread finds tasks stuck in `RUNNING` past `TASK_LEASE_SECONDS` (a crashed
worker) and requeues them (or fails them if exhausted). *Why:* a claimed task
whose worker dies would otherwise block its execution forever.

**Delayed-retry queue.** Retries are scheduled in a Redis sorted set keyed by
run-at time; a promoter thread moves due items back onto the main queue. This is
how backoff is realized without blocking a worker.

**Real-time updates (SSE).** `GET /api/executions/{id}/events` streams execution
+ task state to the browser via Server-Sent Events, so the UI shows *started /
completed / failed / retrying / final aggregation* live without polling.

**Structured logging.** Every log line carries `execution_id` and `task_id`
(text or `LOG_FORMAT=json`), so a single execution can be traced across workers.

> **Try it:** submit a request containing the word `force_fail` — the mock
> provider makes agent calls fail, so you can watch retries in the activity log
> and the task land in the dead-letter queue.

### Tests

```bash
cd backend && source .venv/bin/activate
pytest -q
```
Covers retry behaviour, timeout handling, idempotency, task state transitions,
and crash recovery.

---

## Tools & tool calling (Phase 4)

Agents don't just prompt an LLM — they can call **tools** through structured
tool/function calling, turning the platform into a real agent runtime rather
than a task queue.

**Registered tools** (`app/tools/`):
- `calculator` — safe arithmetic (AST-based; no `eval`).
- `web_search` — top-result snippets (offline mock by default; swap in a real
  backend).
- `fetch_url` — fetch text at an http(s) URL (real network, size-capped).

**How it works.** Each agent advertises a set of tools (research →
web_search/fetch_url, analysis → calculator/fetch_url, summarization → none).
The agent runs a **tool-calling loop**: the LLM may return tool calls, which are
executed and fed back as observations, until the model produces a final answer
(bounded by `AGENT_MAX_TOOL_ITERATIONS`). Every tool runs under
`TOOL_TIMEOUT_SECONDS`; failures and timeouts are returned to the agent as safe
error observations rather than crashing the task. Each invocation is logged.

The abstraction is provider-agnostic: the **mock** provider performs the loop
offline (deterministically), while the OpenAI and Anthropic providers map it to
their native function-calling APIs.

## Observability (Phase 4)

Tracked per task and per execution and persisted to the DB: **duration**,
**LLM token usage**, **estimated cost** (from a small pricing table), and
**tool-call counts**. Logs are structured with `execution_id`, `task_id` and
`agent`.

- `GET /api/metrics` — JSON summary (counts by status, avg/max durations, total
  tokens, total estimated cost, tool calls, queue depths).
- `GET /metrics` — the same data in Prometheus text-exposition format.

Metrics are **derived from the database on demand** (accurate across the API and
all workers) plus live Redis queue depths — no separate metrics store to run.
The UI shows an execution **timeline**, per-task stats, and a platform-metrics
panel.

---

## Production deployment (Phase 5)

A production-style stack is defined in `docker-compose.prod.yml`: the frontend is
built to static files and served by **nginx** (which also reverse-proxies the API
and streams SSE), the backend runs multiple **uvicorn workers**, **API-key auth**
and **rate limiting** are enabled, logs are **JSON**, datastore ports are not
exposed, and every service has a `restart` policy.

```bash
# API_KEY is required for the prod stack
API_KEY=$(openssl rand -hex 16) podman compose -f docker-compose.prod.yml up --build -d
# scale workers horizontally
API_KEY=... podman compose -f docker-compose.prod.yml up --build -d --scale worker=3
```

The UI is served at http://localhost:8080 and calls the API through nginx.

**Security**
- API-key auth on all `/api/*` routes (header, bearer, or `?api_key=` for SSE).
- Per-client rate limiting and a request-body size cap.
- Secrets (API key, LLM keys, DB password) come from environment variables and
  are never logged.
- `/health` reports liveness plus DB/Redis readiness; workers shut down
  gracefully on SIGTERM (in-flight tasks finish or are recovered by the reaper).

## Performance / load test

A dependency-free load test fires N executions concurrently and reports
throughput and latency:

```bash
python scripts/loadtest.py --base http://localhost:8000 --count 100 --concurrency 25
```

Sample run on the dev Podman stack (Postgres + Redis + **one** worker with 4
threads, mock LLM, on a laptop):

| Executions | Concurrency | Wall time | Throughput | p50 / p95 latency | Result |
|---|---|---|---|---|---|
| 30 | 10 | 1.74 s | 17.3 exec/s | 0.36 s / 0.83 s | 30/30 ✅ |
| 100 | 25 | 6.12 s | 16.3 exec/s | 1.43 s / 2.68 s | 100/100 ✅ |

That's ~300 agent tasks (100 executions × 3) processed in ~6 s. Throughput scales
by raising `WORKER_CONCURRENCY` or running more worker containers (`--scale
worker=N`); with a real LLM, latency is dominated by model calls and
concurrency matters much more.

## Continuous integration

`.github/workflows/ci.yml` runs three jobs on every push/PR:
- **lint** — `ruff check`
- **unit-tests** — `pytest -m "not integration"`
- **integration-tests** — spins up Postgres + Redis services and runs the
  full-flow integration test (`pytest -m integration`).

Run locally:
```bash
cd backend && source .venv/bin/activate
ruff check .
pytest -q            # unit + integration (integration needs Redis)
```

## Screenshots

> Add dashboard images to `docs/` and reference them here, e.g.
> `![Dashboard](docs/dashboard.png)`. The dashboard (http://localhost:5173)
> shows the live task timeline, per-task stats, activity log and platform metrics.

---

## Roadmap

- **Phase 1:** end-to-end MVP, sequential execution ✅
- **Phase 2:** Redis job queue + distributed workers, concurrent tasks, real-time UI ✅
- **Phase 3:** retries, backoff, timeouts, idempotency, dead-letter queue, crash recovery, SSE ✅
- **Phase 4:** agent tools (calculator, web search, fetch) + observability / `/metrics` ✅
- **Phase 5:** auth, rate limiting, health checks, graceful shutdown, DB indexes, prod Docker, CI, integration + load tests ✅

The project is considered complete.
