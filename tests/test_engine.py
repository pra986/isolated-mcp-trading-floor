import pytest

from trading_floor import DuplicateTickError, IsolatedMCPTradingFloor


def test_cross_persona_memory_isolation():
    floor = IsolatedMCPTradingFloor(":memory:")
    try:
        floor.register_persona("warren_value", "Warren", "Value", 100_000.0)
        floor.register_persona("george_macro", "George", "Macro", 100_000.0)

        floor.write_memory("warren_value", "thesis", "Buy undervalued compounders")
        floor.write_memory("george_macro", "thesis", "Short duration bonds")

        warren_mem = floor.read_memory("warren_value")
        george_mem = floor.read_memory("george_macro")

        assert len(warren_mem) == 1
        assert warren_mem[0].namespace == "memory://warren_value"
        assert warren_mem[0].value == "Buy undervalued compounders"

        assert len(george_mem) == 1
        assert george_mem[0].namespace == "memory://george_macro"
        assert george_mem[0].value == "Short duration bonds"
    finally:
        floor.close()


def test_market_closed_schedule_skipping():
    floor = IsolatedMCPTradingFloor(":memory:")
    try:
        floor.register_persona("warren_value", "Warren", "Value", 50_000.0)
        result = floor.execute_tick(
            tick_run_id="tick-closed-001",
            persona_id="warren_value",
            symbol="AAPL",
            side="BUY",
            quantity=5,
            price=200.0,
            market_open=False,
        )
        assert result["status"] == "skipped_market_closed"
        assert result["receipt"] is None
        acc = floor.get_account("warren_value")
        assert acc.cash_balance == 50_000.0
        assert acc.positions == {}
    finally:
        floor.close()


def test_duplicate_tick_run_id_rejection():
    floor = IsolatedMCPTradingFloor(":memory:")
    try:
        floor.register_persona("warren_value", "Warren", "Value", 10_000.0)
        first = floor.execute_tick(
            tick_run_id="tick-dup-001",
            persona_id="warren_value",
            symbol="MSFT",
            side="BUY",
            quantity=2,
            price=400.0,
            market_open=True,
        )
        assert first["status"] == "executed"

        with pytest.raises(DuplicateTickError):
            floor.execute_tick(
                tick_run_id="tick-dup-001",
                persona_id="warren_value",
                symbol="MSFT",
                side="BUY",
                quantity=2,
                price=400.0,
                market_open=True,
            )

        acc = floor.get_account("warren_value")
        assert acc.cash_balance == 9_200.0
        assert acc.positions == {"MSFT": 2}
    finally:
        floor.close()


def test_failed_research_mcp_server_isolation():
    floor = IsolatedMCPTradingFloor(":memory:")
    try:
        floor.register_persona("george_macro", "George", "Macro", 25_000.0)

        def healthy_mcp(symbol: str) -> str:
            return f"ok:{symbol}"

        def broken_mcp(symbol: str) -> str:
            raise ConnectionError("MCP research server unreachable")

        result = floor.execute_tick(
            tick_run_id="tick-fault-001",
            persona_id="george_macro",
            symbol="NVDA",
            side="BUY",
            quantity=10,
            price=100.0,
            market_open=True,
            research_servers={"sec_mcp": healthy_mcp, "news_mcp": broken_mcp},
        )
        assert result["status"] == "executed"
        assert "news_mcp" in result["failed_servers"]
        assert result["research"] == {"sec_mcp": "ok:NVDA"}

        acc = floor.get_account("george_macro")
        assert acc.cash_balance == 24_000.0
        assert acc.positions == {"NVDA": 10}
    finally:
        floor.close()
