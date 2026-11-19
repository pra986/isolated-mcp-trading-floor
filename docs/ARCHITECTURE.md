# Architecture Overview

`isolated-mcp-trading-floor` implements a multi-persona autonomous trading floor where each trader persona operates inside strict memory, ledger, and MCP tool-execution boundaries.

## Core Design Principles

1. **Per-Persona Memory Namespace Isolation**
   - Every memory entry (`MCPMemoryEntry`) is scoped to a `persona_id` and stored under an isolated namespace (`memory://<persona_id>`).
   - Queries from one persona never read or leak memory entries belonging to another persona.

2. **Market-Hours Scheduling Gate**
   - Trading ticks are gated by a configurable market-hours check (`market_open: bool`).
   - When the market is closed, scheduled runs are skipped cleanly with `status="skipped_market_closed"` without mutating accounts or memory.

3. **Tick-Level Idempotency (`tick_run_id`)**
   - Every execution tick requires a unique `tick_run_id`.
   - Processed `tick_run_id` values are persisted in SQLite (`processed_ticks` table) inside the same transaction as ledger updates.
   - Duplicate `tick_run_id` submissions are rejected (`DuplicateTickError` or idempotent rejection) to prevent double-execution.

4. **Transactional SQLite Account Ledger**
   - `TraderPersonaAccount` balances and trade receipts (`MCPTradeReceipt`) are stored in SQLite with `BEGIN IMMEDIATE` / atomic transaction semantics.
   - Cash and position updates only commit if all validation checks (sufficient cash, valid quantity) succeed.

5. **Fault Isolation for Research MCP Servers**
   - Research MCP servers run behind per-server fault boundaries.
   - If a research MCP server raises an exception or times out, the failure is captured in the tick result (`failed_servers`) while healthy servers and the SQLite ledger remain uncorrupted.

## Component Map

- `trading_floor/models.py`: Dataclasses for `TraderPersonaAccount`, `MCPMemoryEntry`, and `MCPTradeReceipt`.
- `trading_floor/engine.py`: `IsolatedMCPTradingFloor` orchestrator with SQLite persistence, memory isolation, market gate, idempotency, and MCP fault isolation.
- `trading_floor/cli.py`: Runnable CLI demonstration entrypoint.
- `evaluation/eval_cases.json`: Structured evaluation scenarios for isolation, scheduling, idempotency, and fault tolerance.
