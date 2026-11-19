import sqlite3
from typing import Any, Callable, Dict, List, Optional

from .models import MCPMemoryEntry, MCPTradeReceipt, TraderPersonaAccount


class DuplicateTickError(ValueError):
    """Raised when a tick_run_id has already been processed."""


class InsufficientFundsError(ValueError):
    """Raised when a persona lacks cash or shares for a trade."""


class IsolatedMCPTradingFloor:
    """Orchestrates isolated trader personas with SQLite transactionality."""

    def __init__(self, db_path: str = ":memory:") -> None:
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self) -> None:
        with self.conn:
            self.conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS accounts (
                    persona_id TEXT PRIMARY KEY,
                    display_name TEXT NOT NULL,
                    strategy TEXT NOT NULL,
                    cash_balance REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS positions (
                    persona_id TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    quantity INTEGER NOT NULL,
                    PRIMARY KEY (persona_id, symbol)
                );
                CREATE TABLE IF NOT EXISTS persona_memory (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    persona_id TEXT NOT NULL,
                    namespace TEXT NOT NULL,
                    mem_key TEXT NOT NULL,
                    mem_value TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS processed_ticks (
                    tick_run_id TEXT PRIMARY KEY,
                    persona_id TEXT NOT NULL,
                    processed_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS trade_receipts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tick_run_id TEXT NOT NULL,
                    persona_id TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    side TEXT NOT NULL,
                    quantity INTEGER NOT NULL,
                    price REAL NOT NULL,
                    total_amount REAL NOT NULL,
                    executed_at TEXT NOT NULL
                );
                """
            )

    def register_persona(
        self,
        persona_id: str,
        display_name: str,
        strategy: str,
        initial_cash: float = 100_000.0,
    ) -> TraderPersonaAccount:
        with self.conn:
            self.conn.execute(
                """
                INSERT OR IGNORE INTO accounts (persona_id, display_name, strategy, cash_balance)
                VALUES (?, ?, ?, ?)
                """,
                (persona_id, display_name, strategy, initial_cash),
            )
        return self.get_account(persona_id)

    def get_account(self, persona_id: str) -> TraderPersonaAccount:
        row = self.conn.execute(
            "SELECT persona_id, display_name, strategy, cash_balance FROM accounts WHERE persona_id = ?",
            (persona_id,),
        ).fetchone()
        if row is None:
            raise KeyError(f"Unknown persona_id: {persona_id}")
        pos_rows = self.conn.execute(
            "SELECT symbol, quantity FROM positions WHERE persona_id = ? AND quantity != 0",
            (persona_id,),
        ).fetchall()
        positions = {r["symbol"]: int(r["quantity"]) for r in pos_rows}
        return TraderPersonaAccount(
            persona_id=row["persona_id"],
            display_name=row["display_name"],
            strategy=row["strategy"],
            cash_balance=float(row["cash_balance"]),
            positions=positions,
        )

    def write_memory(self, persona_id: str, key: str, value: str) -> MCPMemoryEntry:
        account = self.get_account(persona_id)
        entry = MCPMemoryEntry(
            persona_id=persona_id,
            namespace=account.memory_namespace,
            key=key,
            value=value,
        )
        with self.conn:
            self.conn.execute(
                """
                INSERT INTO persona_memory (persona_id, namespace, mem_key, mem_value, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (entry.persona_id, entry.namespace, entry.key, entry.value, entry.created_at),
            )
        return entry

    def read_memory(self, persona_id: str, key: Optional[str] = None) -> List[MCPMemoryEntry]:
        account = self.get_account(persona_id)
        if key is None:
            rows = self.conn.execute(
                """
                SELECT persona_id, namespace, mem_key, mem_value, created_at
                FROM persona_memory
                WHERE persona_id = ? AND namespace = ?
                ORDER BY id ASC
                """,
                (persona_id, account.memory_namespace),
            ).fetchall()
        else:
            rows = self.conn.execute(
                """
                SELECT persona_id, namespace, mem_key, mem_value, created_at
                FROM persona_memory
                WHERE persona_id = ? AND namespace = ? AND mem_key = ?
                ORDER BY id ASC
                """,
                (persona_id, account.memory_namespace, key),
            ).fetchall()
        return [
            MCPMemoryEntry(
                persona_id=r["persona_id"],
                namespace=r["namespace"],
                key=r["mem_key"],
                value=r["mem_value"],
                created_at=r["created_at"],
            )
            for r in rows
        ]

    def run_research_servers(
        self,
        servers: Dict[str, Callable[[str], Any]],
        symbol: str,
    ) -> Dict[str, Any]:
        results: Dict[str, Any] = {}
        failed_servers: Dict[str, str] = {}
        for name, fn in servers.items():
            try:
                results[name] = fn(symbol)
            except Exception as exc:
                failed_servers[name] = str(exc)
        return {"results": results, "failed_servers": failed_servers}

    def execute_tick(
        self,
        tick_run_id: str,
        persona_id: str,
        symbol: str,
        side: str,
        quantity: int,
        price: float,
        market_open: bool = True,
        research_servers: Optional[Dict[str, Callable[[str], Any]]] = None,
    ) -> Dict[str, Any]:
        if not market_open:
            return {
                "status": "skipped_market_closed",
                "tick_run_id": tick_run_id,
                "persona_id": persona_id,
                "receipt": None,
                "failed_servers": {},
            }

        research_report = self.run_research_servers(research_servers or {}, symbol)
        side_upper = side.upper()
        if side_upper not in {"BUY", "SELL"}:
            raise ValueError(f"Unsupported trade side: {side}")
        if quantity <= 0 or price <= 0:
            raise ValueError("Quantity and price must be positive")

        total_amount = round(quantity * price, 2)
        receipt = MCPTradeReceipt(
            tick_run_id=tick_run_id,
            persona_id=persona_id,
            symbol=symbol,
            side=side_upper,
            quantity=quantity,
            price=price,
            total_amount=total_amount,
        )

        with self.conn:
            existing = self.conn.execute(
                "SELECT tick_run_id FROM processed_ticks WHERE tick_run_id = ?",
                (tick_run_id,),
            ).fetchone()
            if existing is not None:
                raise DuplicateTickError(f"Duplicate tick_run_id: {tick_run_id}")

            acc = self.get_account(persona_id)
            current_qty = acc.positions.get(symbol, 0)

            if side_upper == "BUY":
                if acc.cash_balance < total_amount:
                    raise InsufficientFundsError("Insufficient cash balance")
                new_cash = round(acc.cash_balance - total_amount, 2)
                new_qty = current_qty + quantity
            else:
                if current_qty < quantity:
                    raise InsufficientFundsError("Insufficient share position")
                new_cash = round(acc.cash_balance + total_amount, 2)
                new_qty = current_qty - quantity

            self.conn.execute(
                "UPDATE accounts SET cash_balance = ? WHERE persona_id = ?",
                (new_cash, persona_id),
            )
            self.conn.execute(
                """
                INSERT INTO positions (persona_id, symbol, quantity)
                VALUES (?, ?, ?)
                ON CONFLICT(persona_id, symbol) DO UPDATE SET quantity = excluded.quantity
                """,
                (persona_id, symbol, new_qty),
            )
            self.conn.execute(
                "INSERT INTO processed_ticks (tick_run_id, persona_id, processed_at) VALUES (?, ?, ?)",
                (tick_run_id, persona_id, receipt.executed_at),
            )
            self.conn.execute(
                """
                INSERT INTO trade_receipts
                (tick_run_id, persona_id, symbol, side, quantity, price, total_amount, executed_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    receipt.tick_run_id,
                    receipt.persona_id,
                    receipt.symbol,
                    receipt.side,
                    receipt.quantity,
                    receipt.price,
                    receipt.total_amount,
                    receipt.executed_at,
                ),
            )

        return {
            "status": "executed",
            "tick_run_id": tick_run_id,
            "persona_id": persona_id,
            "receipt": receipt,
            "research": research_report["results"],
            "failed_servers": research_report["failed_servers"],
        }

    def close(self) -> None:
        self.conn.close()
