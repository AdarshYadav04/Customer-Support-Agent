# Ecommerce Support Agent

Multi-agent customer support for an online store.
FastAPI · Pydantic · SQLAlchemy (async) · Postgres · OpenAI **Responses API** through your **LiteLLM proxy**.

## How it works

```
POST /v1/chat
   │
   ▼
Guardrail (LLM classifier) ── off-topic / injection / abusive ──► friendly denial (no agents run)
   │ allowed
   ▼
Orchestrator agent ── delegates (as tools) ──┬─► order_status_agent ─► get_order_status, list_recent_orders
                                             ├─► returns_agent      ─► check_return_eligibility, create_return_request
                                             └─► product_agent      ─► search_products, get_product
                                                         │
                                                         ▼
                                                     Postgres
```

- **Guardrail**: a cheap model classifies every message first. Invalid classifier output fails closed (HTTP 503); it never lets a message through unchecked.
- **Orchestrator** never states facts itself; it calls specialist agents, each with its own prompt and tools.
- **Customer isolation**: `customer_id` comes from authentication and is injected into tools via `RunContext`; the model cannot choose it.
- **Writes are re-validated** in code (return eligibility is checked again inside `create_return_request`).
- Conversation history lives in Postgres (`store=False` on the Responses API), so any worker can serve any turn.

## Layout

```
app/
  main.py               app factory + lifespan wiring
  core/                 settings (pydantic-settings), logging
  api/                  routes, schemas, dependencies (auth, DB session)
  services/chat.py      one chat turn: history → guardrail → orchestrator → persist
  agents/
    base.py             Agent, Tool (Pydantic-validated), RunContext
    runner.py           tool-calling loop for the Responses API
    guardrail.py        input guardrail + denial messages
    orchestrator.py     main agent, specialists exposed as tools
    specialists/        order_status.py · returns.py · product.py
  llm/client.py         Responses API client (OpenAI SDK → LiteLLM proxy)
  db/                   models, repositories, session, seed
tests/                  fake-LLM tests, SQLite in memory
```

## Setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e '.[dev]'
cp .env.example .env        # fill in the three required values below
```

`.env` (required):

| Variable | Example |
|---|---|
| `DATABASE_URL` | `postgresql+asyncpg://user:pass@host:5432/support` (plain `postgresql://` also works) |
| `LITELLM_PROXY_URL` | `http://your-proxy:4000/v1` |
| `LITELLM_PROXY_KEY` | your LiteLLM virtual/master key |

Also set `AGENT_MODEL` / `GUARDRAIL_MODEL` to model names that exist on your proxy (defaults: `gpt-4.1`, `gpt-4.1-mini`).
The proxy must expose the Responses API (`/v1/responses`).

## Run

```bash
python -m app.db.seed                 # creates tables + demo data (customers 1 and 2)
uvicorn app.main:app --reload
```

```bash
curl -s localhost:8000/v1/chat \
  -H 'Content-Type: application/json' -H 'X-Customer-Id: 1' \
  -d '{"message": "Where is my order ORD-1002?"}'

# off-topic -> friendly denial, "blocked": true
curl -s localhost:8000/v1/chat \
  -H 'Content-Type: application/json' -H 'X-Customer-Id: 1' \
  -d '{"message": "Write me a poem about the moon"}'
```

Pass the returned `conversation_id` in the next request to continue the conversation.
Demo data for customer 1: `ORD-1001` (delivered, returnable), `ORD-1002` (shipped), `ORD-1003` (outside return window).
Health checks: `GET /health`, `GET /ready` (checks the database).

Tests: `pytest`

## Add a new specialist

1. Create `app/agents/specialists/<name>.py` with Pydantic arg models, async tool handlers and a `build_<name>_agent()`.
2. Add it to the `specialists` list in `app/agents/orchestrator.py` and mention it in the orchestrator prompt.

## Before going live

- **Auth**: `X-Customer-Id` is trusted as-is (fine behind a gateway that authenticates users). Replace `get_current_customer` in `app/api/deps.py` with JWT/session auth if exposed directly. `SERVICE_API_KEY` adds an `X-API-Key` check.
- **Migrations**: tables are created with `create_all` (`AUTO_CREATE_TABLES=true` or the seed script). Add Alembic once the schema starts evolving.
- **Seed data**: don't run `app.db.seed` against a production database.
- **Rate limiting, spend limits**: rate-limit at your gateway; use per-key budgets on the LiteLLM proxy.
