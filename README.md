# GenkiAgent — Enterprise Channel Management AI Agent

> **Ontology + MCP + Claude** applied to real-world channel operations.  
> A working reference implementation of the three-layer enterprise Agent architecture.

---

## What This Is

Most enterprise AI projects stall because LLMs can't make sense of raw business data.
Fields like `ord_amt_v2`, `sts_cd`, `cust_tp_cd` carry no semantic meaning on their own —
and without a semantic layer, an agent reasoning over them is guessing.

This project implements a concrete solution:
a channel management agent for **Genki Forest (元气森林)**
that uses an **Ontology layer** to give Claude structured business context before every reasoning step.

It is also a working proof-of-concept for the three-layer architecture
described in [`docs/architecture.md`](./docs/architecture.md).

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                     HTTP API  (FastAPI)                  │
│   POST /chat   POST /approve   GET /approvals            │
└───────────────────────────┬─────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────┐
│              GenkiOrchestrator  (Claude claude-sonnet)   │
│                                                         │
│  ReAct loop: Thought → Tool Call → Observation → …      │
│  Parallel tool calls supported (tool_use stop reason)   │
│  Conversation history maintained across turns           │
└──────────────┬──────────────────────────┬──────────────┘
               │                          │
               ▼                          ▼
┌──────────────────────┐    ┌─────────────────────────────┐
│  ontology_mcp.py     │    │  action_mcp.py               │
│  (Read tools)        │    │  (Write tools)               │
│                      │    │                              │
│  search_objects      │    │  create_sales_order          │
│  get_object          │    │  confirm_order_shipment      │
│  semantic_search     │    │  create_listing_task         │
│  get_inventory       │    │  update_listing_status       │
│  get_linked_objects  │    │  create_promotion            │
│  get_channel_        │    │  approve_action              │
│    coverage          │    │  get_pending_approvals       │
│  get_sales_summary   │    │                              │
└──────────┬───────────┘    └──────────────┬──────────────┘
           │                               │
           └──────────────┬────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────┐
│           OntologyStorage  (PostgreSQL + pgvector)       │
│                                                         │
│  ontology_objects   — all business objects (JSONB)      │
│  ontology_links     — object relationships              │
│  action_logs        — audit trail + approval queue      │
└─────────────────────────────────────────────────────────┘
```

### Three-layer design

| Layer | File | Responsibility |
|-------|------|----------------|
| **Ontology** | `ontology/schema.py`, `ontology/storage.py` | Business object definitions, vector storage, audit log |
| **MCP Server** | `mcp/ontology_mcp.py`, `mcp/action_mcp.py` | Wraps all business operations as typed tools for the agent |
| **Agent** | `agents/orchestrator.py` | ReAct reasoning loop; calls tools, maintains history, routes to approvals |

**Key design principle:** the Ontology is *not* in the call chain.
It serves two independent paths — loading context for LLM reasoning *and* receiving writeback from MCP executions — without coupling the two.

---

## Ontology Schema

Ten business object types, modeled on the Genki Forest channel structure:

| Object Type | Description |
|-------------|-------------|
| `Brand` | Brand lines (Genki Forest, Alienergy) |
| `Product` | Product lines (Sparkling Water, Energy Drink) |
| `SKU` | Specific variants with pricing and reorder thresholds |
| `Channel` | Channel types: KA / CVS / Ecom / HoReCa |
| `Distributor` | Regional distributors with credit limits |
| `Store` | Retail endpoints, tiered A/B/C, linked to distributor |
| `InventoryRecord` | SKU × Distributor stock snapshot |
| `SalesOrder` | Store → Distributor purchase orders |
| `Promotion` | Discount campaigns with budget controls |
| `ListingTask` | SKU-to-store listing tracking (key channel KPI) |

Relationships are stored in `ontology_links` and traversable via `get_linked_objects`.

---

## Human-in-the-Loop Approvals

Write operations above defined thresholds automatically enter a `pending` state
and are queued for human review before execution.

| Action | Threshold | Behavior |
|--------|-----------|----------|
| `create_sales_order` | Total ≥ ¥50,000 | Written to `action_logs` with `approval_status=pending` |
| `create_promotion` | Budget ≥ ¥100,000 | Same — agent returns `action_id` to caller |
| `suspend_distributor` | Always | Always requires approval |
| `adjust_inventory` | Delta ≤ -500 units | Negative adjustments above threshold |

Approve or reject via `POST /approve` or the `approve_action` tool.

---

## Quick Start

### Prerequisites
- Docker + Docker Compose
- An Anthropic API key

### Run

```bash
git clone https://github.com/leosun/genki-agent.git
cd genki-agent

cp .env.example .env
# Edit .env — set ANTHROPIC_API_KEY at minimum

docker-compose up --build
```

The API will be available at `http://localhost:8000`.

### Seed sample data

```bash
curl -X POST http://localhost:8000/seed
```

This writes 2 brands, 2 products, 3 SKUs, 2 distributors, 3 stores,
inventory records, and listing tasks to the database.

### Try a conversation

```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "查询上海锐进贸易的渠道覆盖情况"}'
```

```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "帮我给全家人民广场店下一个气泡水白桃味500ml的订单，500件"}'
```

---

## API Reference

### `POST /chat`
```json
{ "message": "string", "reset": false }
```
Returns the agent reply and last 10 tool calls for debugging.

### `POST /approve`
```json
{
  "action_id": "uuid",
  "approved_by": "manager_01",
  "approved": true,
  "rejection_reason": ""
}
```

### `GET /approvals`
Returns all actions currently pending human approval.

### `POST /seed`
Populates the database with Genki Forest demo data.

---

## Local Dev (without Docker)

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Start Postgres locally (or point DATABASE_URL at an existing instance)
# Then:
uvicorn api.main:app --reload
```

Semantic search works without `OPENAI_API_KEY` — a deterministic mock embedding
is used automatically. Replace with real embeddings for production.

---

## Project Structure

```
genki-agent/
├── api/
│   ├── main.py              # FastAPI app, lifespan, endpoints
│   └── seed.py              # Demo data seeding
├── ontology/
│   ├── schema.py            # Object/Link/Action type definitions + registry
│   ├── storage.py           # PostgreSQL + pgvector CRUD, semantic search, audit log
│   └── embeddings.py        # OpenAI embedding with mock fallback
├── mcp/
│   ├── ontology_mcp.py      # Read tools (search, get, inventory, coverage)
│   └── action_mcp.py        # Write tools (orders, listing, promotions, approvals)
├── agents/
│   ├── orchestrator.py      # GenkiOrchestrator — ReAct loop, tool dispatch
│   └── tool_definitions.py  # Tool schemas in Anthropic API format
├── docs/
│   ├── architecture.md      # Architecture deep-dive
│   └── api-reference.md     # Full API docs
├── docker-compose.yml       # Postgres (pgvector) + API service
├── Dockerfile
├── requirements.txt
└── .env.example
```

---

## Tech Stack

| Component | Choice |
|-----------|--------|
| LLM | Claude (`claude-sonnet-4-6`) via Anthropic API |
| Agent pattern | ReAct (custom loop, no framework overhead) |
| Tool protocol | Anthropic native tool calling |
| Storage | PostgreSQL 16 + pgvector (1536-dim cosine similarity) |
| Embeddings | OpenAI `text-embedding-3-small` (mock fallback included) |
| API | FastAPI + uvicorn |
| Containerization | Docker Compose |

---

## References

- [Palantir Ontology](https://www.palantir.com/platforms/foundry/ontology/) — architectural inspiration
- [ReAct: Synergizing Reasoning and Acting in Language Models](https://arxiv.org/abs/2210.03629)
- [Anthropic Tool Use docs](https://docs.anthropic.com/en/docs/build-with-claude/tool-use)

---

## Author

Sun Shaolei · AI Application Architect  
shaolei.sun@gmail.com | [github.com/sunshaolei](https://github.com/sunshaolei)
