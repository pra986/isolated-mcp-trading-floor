# Isolated MCP Trading Floor (Project 25)

**A8: Agentic Track — MCP Trading Floor**

Four-persona autonomous Model Context Protocol (MCP) trading floor with isolated per-trader memory namespaces, market-hours gates, `tick_run_id` idempotency, and transactional SQLite accounts.

---

## Architecture

The system coordinates four distinct autonomous trading personas over standardized MCP tool servers while guaranteeing strict state, memory, and ledger isolation between traders:

- **Trader Personas (4):**
  - **Value (`warren`)** — Fundamental long-term value investing.
  - **Macro (`george`)** — Global macro, rates, and currency-driven positioning.
  - **Systematic (`ray`)** — Risk-parity and diversified factor allocation.
  - **Innovation (`cathie`)** — High-conviction disruptive growth equities.
- **MCP Server Topology:**
  - **Accounts MCP Server** — Exposes `get_account`, `buy_shares`, `sell_shares`, `get_holdings`, and `get_transactions` backed by transactional SQLite.
  - **Market Data MCP Server** — Exposes `lookup_share_price`, `is_market_open`, and historical/snapshot quotes with deterministic offline fallback.
  - **Memory MCP Server** — Namespaced per-trader SQLite/graph memory (`memory_<trader_id>`) preventing cross-persona memory leakage.
  - **Audit & Notification MCP Server** — Records structured tick logs and trade alerts keyed by `tick_run_id`.

---

## 6-Stage Workflow

1. **Market-Hours Gate:** Evaluates exchange calendar and market-hours rules (with configurable override for backtest/paper simulation). Halts trade execution cleanly when the market is closed.
2. **Idempotent Tick Initialization (`tick_run_id`):** Registers a unique `tick_run_id` per `(trader_id, schedule_slot)` in SQLite. Duplicate or retried triggers with an already-committed `tick_run_id` short-circuit without re-executing orders.
3. **Isolated Context & Memory Hydration:** Loads only the active trader's account state, open positions, and isolated memory namespace (`namespace=trader_id`).
4. **Persona Research & Decision Loop:** The trader agent queries Market Data and Memory MCP tools within a bounded turn budget to formulate buy/sell/hold decisions.
5. **Transactional SQLite Settlement:** Executes `buy_shares` / `sell_shares` inside an atomic SQLite transaction (`BEGIN IMMEDIATE ... COMMIT` / `ROLLBACK` on insufficient funds or shares), updating cash, holdings, and `transactions` together.
6. **Valuation, Reflection & Audit Commit:** Computes mark-to-market portfolio value, persists post-trade reflections to the trader's isolated memory namespace, and marks `tick_run_id` as `committed`.

---

## Data Contract

| Entity | Key Fields | Guarantees |
| --- | --- | --- |
| `Account` | `name`, `balance`, `strategy`, `holdings_json`, `portfolio_value_time_series` | Non-negative cash balance; atomic updates |
| `Transaction` | `id`, `account_name`, `symbol`, `quantity`, `price`, `timestamp`, `rationale` | Append-only ledger tied to settled trades |
| `TickRun` | `tick_run_id`, `trader_id`, `status` (`started`/`committed`/`skipped`), `created_at` | Primary-key uniqueness enforces idempotency |
| `MemoryEntry` | `namespace` (`trader_id`), `entity`, `observation`, `updated_at` | Strict `WHERE namespace = ?` isolation |

---

## Production Controls

- **Isolated Per-Trader Memory Namespaces:** Every memory read/write requires an explicit `trader_id` namespace; cross-trader queries are rejected at the storage layer.
- **Market-Hours Gates:** Prevents live or simulated order placement outside configured trading windows unless `FORCE_MARKET_OPEN=true` is explicitly set for testing.
- **`tick_run_id` Idempotency:** Safely handles scheduler retries and crash recovery without double-buying or double-selling.
- **Transactional SQLite Accounts:** Uses WAL mode and `BEGIN IMMEDIATE` transactions with rollback on validation or constraint errors.
- **No Unaudited Side Effects:** Secrets and API keys are loaded strictly from environment variables (`.env`), never hardcoded.

---

## Local Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
pytest
```

---

## Attribution

Architecture and domain foundation adapted with pinned attribution from `ed-donner/agents` (`6_mcp/backend`).
 gates, tick_run_id idempotency, and transactional SQLite accounts.
