from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class TraderPersonaAccount:
    persona_id: str
    display_name: str
    strategy: str
    cash_balance: float
    positions: Dict[str, int] = field(default_factory=dict)

    @property
    def memory_namespace(self) -> str:
        return f"memory://{self.persona_id}"


@dataclass(frozen=True)
class MCPMemoryEntry:
    persona_id: str
    namespace: str
    key: str
    value: str
    created_at: str = field(default_factory=utc_now_iso)


@dataclass(frozen=True)
class MCPTradeReceipt:
    tick_run_id: str
    persona_id: str
    symbol: str
    side: str
    quantity: int
    price: float
    total_amount: float
    executed_at: str = field(default_factory=utc_now_iso)
