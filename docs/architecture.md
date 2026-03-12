# Architecture Deep-Dive

## The Semantic Layer Problem

Enterprise systems are built for humans, not LLMs.
A field named `sts_cd` with value `07` is perfectly readable to a developer who knows the codebook.
To an LLM, it is opaque — without knowing that `07` means "logistics exception — pending review",
the model cannot reason about what action is appropriate.

The Ontology layer solves this by maintaining a mapping from raw system fields
to semantically rich business definitions. Before every reasoning step,
the agent loads this context and injects it into the LLM's prompt.

---

## Why Not Just Put Everything in the System Prompt

A static system prompt can carry basic domain knowledge,
but it cannot capture the *current state* of the business:
which distributors are suspended today, what the inventory levels are right now,
which listing tasks are overdue.

The Ontology is a **live** business model. It is queried at runtime,
so the agent always reasons over current data, not stale descriptions.

---

## The Three Layers in Practice

### 1. Ontology Layer (`ontology/`)

Defines what business objects exist and what they mean.

`schema.py` registers all Object Types using a decorator pattern:

```python
@ontology_object
@dataclass
class Distributor:
    status: str = "active"   # LLM knows: only "active" distributors can receive orders
    credit_limit: float = 0.0
    outstanding_amount: float = 0.0
```

`storage.py` provides:
- `upsert_object` / `get_object` / `query_objects` — structured CRUD
- `semantic_search` — pgvector cosine similarity for natural language queries
- `get_linked_objects` — relationship graph traversal
- `log_action` / `resolve_approval` — audit trail and approval queue

### 2. MCP Server Layer (`mcp/`)

Wraps business operations as typed tools. The agent declares **what to do**;
the MCP layer handles **how to do it** and **whether approval is needed**.

`action_mcp.py` enforces business rules before every write:

```python
async def create_sales_order(store_id, distributor_id, sku_id, quantity, ...):
    # 1. Verify distributor status = "active"
    # 2. Check available_quantity >= quantity
    # 3. Verify outstanding + total <= credit_limit
    # 4. Write SalesOrder object
    # 5. Decide: needs_approval = total_amount >= 50,000
    # 6. Log to action_logs with correct ApprovalStatus
```

This means the agent cannot accidentally create an order for a suspended distributor,
or exceed credit limits, regardless of how it reasons.

### 3. Agent Layer (`agents/`)

`orchestrator.py` implements a straightforward ReAct loop:

```
while not done:
    response = claude.messages.create(tools=TOOLS, messages=history)
    
    if response.stop_reason == "end_turn":
        return response.text
    
    if response.stop_reason == "tool_use":
        results = await parallel_execute(response.tool_use_blocks)
        history.append(tool_results)
        # continue loop
```

All tool calls are dispatched in parallel when multiple `tool_use` blocks
appear in a single response — this is Claude's native behavior when independent
queries can be resolved simultaneously.

---

## Approval Flow

```
Agent calls create_sales_order(quantity=10000, unit_price=6.0)
  → total_amount = 60,000 ≥ 50,000 threshold
  → SalesOrder written with status="pending"
  → ActionLog written with approval_status="pending"
  → Agent returns: "Order created, pending approval. action_id: xxx"

Manager calls POST /approve { action_id: xxx, approved: true }
  → approval_status updated to "approved"
  → inventory locked
  → order status updated to "confirmed"
```

The agent never blocks waiting for approval.
It reports the action_id and continues, allowing other work to proceed.

---

## Semantic Search

Objects are embedded at write time (via `upsert_object` with an `embedding` param).
`seed.py` does not pre-compute embeddings — they are generated on first semantic query
via the `semantic_search` MCP tool, which calls `get_embedding` → `storage.semantic_search`.

pgvector uses IVFFlat index with cosine distance:
```sql
ORDER BY embedding <=> $query_vector
```

The mock embedding in `embeddings.py` is deterministic but not semantically meaningful.
For real semantic search behavior, set `OPENAI_API_KEY`.

---

## Extending the Schema

To add a new Object Type:

1. Add a `@ontology_object @dataclass` class to `ontology/schema.py`
2. Add corresponding tool definitions to `agents/tool_definitions.py`  
3. Add query logic to `mcp/ontology_mcp.py` if a specialized tool is needed
4. Add write logic to `mcp/action_mcp.py` with appropriate approval thresholds
5. Add sample data to `api/seed.py`
