import argparse
import json

from .engine import IsolatedMCPTradingFloor


def run_demo(market_open: bool = True) -> dict:
    floor = IsolatedMCPTradingFloor(":memory:")
    try:
        floor.register_persona("warren_value", "Warren", "Value Investing", 100_000.0)
        floor.register_persona("george_macro", "George", "Global Macro", 100_000.0)

        floor.write_memory("warren_value", "thesis", "Long quality cash-flow compounders")
        floor.write_memory("george_macro", "thesis", "Hedge rate volatility")

        def healthy_research(symbol: str) -> str:
            return f"Fundamentals stable for {symbol}"

        def failing_research(symbol: str) -> str:
            raise RuntimeError("Research MCP server timeout")

        result = floor.execute_tick(
            tick_run_id="demo-tick-001",
            persona_id="warren_value",
            symbol="BRK.B",
            side="BUY",
            quantity=10,
            price=450.0,
            market_open=market_open,
            research_servers={
                "sec_filings_mcp": healthy_research,
                "macro_news_mcp": failing_research,
            },
        )
        warren_acc = floor.get_account("warren_value")
        return {
            "status": result["status"],
            "failed_servers": result["failed_servers"],
            "warren_cash": warren_acc.cash_balance,
            "warren_positions": warren_acc.positions,
        }
    finally:
        floor.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Isolated MCP Trading Floor CLI Demo")
    parser.add_argument("--market-closed", action="store_true", help="Simulate closed market")
    args = parser.parse_args()
    summary = run_demo(market_open=not args.market_closed)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
