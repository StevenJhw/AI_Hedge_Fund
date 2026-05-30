from colorama import Fore, Style
from tabulate import tabulate
from .analysts import ANALYST_ORDER
import os
import json
import textwrap

# Must match portfolio_manager._NON_LLM_AGENTS — data agents that produce signals
# but do not cast a vote toward the final buy/sell decision.
_NON_LLM_AGENTS = {
    "fundamentals_analyst_agent",
    "technical_analyst_agent",
    "sentiment_analyst_agent",
    "valuation_analyst_agent",
    "market_signals_analyst_agent",
    "macro_analyst_agent",
    "earnings_analyst_agent",
    "industry_analyst_agent",
}


def _summarize_reasoning(reasoning) -> str:
    """Convert dict/any reasoning into a readable one-liner summary."""
    if isinstance(reasoning, str):
        return reasoning
    if not isinstance(reasoning, dict):
        return str(reasoning)

    parts = []
    _SIG_MAP = {"bullish": "↑", "bearish": "↓", "neutral": "~"}

    # Technical analyst: keys end with "following", "reversion", "momentum", "volatility", "arbitrage"
    _TA_ABBR = {
        "trend_following": "Trend",
        "mean_reversion": "MR",
        "momentum": "Mom",
        "volatility": "Vol",
        "statistical_arbitrage": "StatArb",
    }
    for key, abbr in _TA_ABBR.items():
        if key in reasoning:
            block = reasoning[key]
            sig = block.get("signal", "?")
            conf = block.get("confidence", 0)
            parts.append(f"{abbr}:{_SIG_MAP.get(sig, sig)}({conf:.0f}%)")
    if parts:
        return " | ".join(parts)

    # Fundamentals analyst: keys end with "_signal"
    _FA_ABBR = {
        "profitability_signal": "Profit",
        "growth_signal": "Growth",
        "financial_health_signal": "Health",
        "price_ratios_signal": "Ratios",
    }
    for key, abbr in _FA_ABBR.items():
        if key in reasoning:
            sig = reasoning[key].get("signal", "?")
            details = reasoning[key].get("details", "")
            parts.append(f"{abbr}:{_SIG_MAP.get(sig, sig)}({details})")
    if parts:
        return " | ".join(parts)

    # Valuation analyst: dcf_analysis, owner_earnings_analysis, etc.
    _VA_ABBR = {
        "dcf_analysis": "DCF",
        "owner_earnings_analysis": "OE",
        "ev_ebitda_analysis": "EV/EBITDA",
        "residual_income_analysis": "RI",
    }
    for key, abbr in _VA_ABBR.items():
        if key in reasoning:
            sig = reasoning[key].get("signal", "?")
            details = reasoning[key].get("details", "")
            # extract just the gap % if present
            gap = ""
            for part in details.split(","):
                if "Gap:" in part:
                    gap = part.strip()
                    break
            parts.append(f"{abbr}:{_SIG_MAP.get(sig, sig)}({gap})")
    if parts:
        return " | ".join(parts)

    # Generic fallback: first-level keys with signal sub-field
    for key, val in reasoning.items():
        if isinstance(val, dict) and "signal" in val:
            sig = val["signal"]
            parts.append(f"{key}:{_SIG_MAP.get(sig, sig)}")
    if parts:
        return " | ".join(parts)

    # Last resort: compact JSON
    return json.dumps(reasoning, separators=(",", ":"))


def sort_agent_signals(signals):
    """Sort agent signals in a consistent order."""
    # Create order mapping from ANALYST_ORDER
    analyst_order = {display: idx for idx, (display, _) in enumerate(ANALYST_ORDER)}
    analyst_order["Risk Management"] = len(ANALYST_ORDER)  # Add Risk Management at the end

    return sorted(signals, key=lambda x: analyst_order.get(x[0], 999))


def print_trading_output(result: dict) -> None:
    """
    Print formatted trading results with colored tables for multiple tickers.

    Args:
        result (dict): Dictionary containing decisions and analyst signals for multiple tickers
    """
    decisions = result.get("decisions")
    if not decisions:
        print(f"{Fore.RED}No trading decisions available{Style.RESET_ALL}")
        return

    # Print decisions for each ticker
    for ticker, decision in decisions.items():
        print(f"\n{Fore.WHITE}{Style.BRIGHT}Analysis for {Fore.CYAN}{ticker}{Style.RESET_ALL}")
        print(f"{Fore.WHITE}{Style.BRIGHT}{'=' * 50}{Style.RESET_ALL}")

        # Prepare analyst signals table for this ticker
        table_data = []
        for agent, signals in result.get("analyst_signals", {}).items():
            if ticker not in signals:
                continue
                
            # Skip Risk Management agent in the signals section
            if agent == "risk_management_agent":
                continue

            signal = signals[ticker]
            agent_name = agent.replace("_agent", "").replace("_", " ").title()
            signal_type = signal.get("signal", "").upper()
            confidence = signal.get("confidence", 0)

            signal_color = {
                "BULLISH": Fore.GREEN,
                "BEARISH": Fore.RED,
                "NEUTRAL": Fore.YELLOW,
            }.get(signal_type, Fore.WHITE)
            
            # Get reasoning if available
            reasoning_str = ""
            if "reasoning" in signal and signal["reasoning"]:
                reasoning_str = textwrap.fill(
                    _summarize_reasoning(signal["reasoning"]),
                    width=60,
                )

            table_data.append(
                [
                    f"{Fore.CYAN}{agent_name}{Style.RESET_ALL}",
                    f"{signal_color}{signal_type}{Style.RESET_ALL}",
                    f"{Fore.WHITE}{confidence}%{Style.RESET_ALL}",
                    f"{Fore.WHITE}{reasoning_str}{Style.RESET_ALL}",
                ]
            )

        # Sort the signals according to the predefined order
        table_data = sort_agent_signals(table_data)

        print(f"\n{Fore.WHITE}{Style.BRIGHT}AGENT ANALYSIS:{Style.RESET_ALL} [{Fore.CYAN}{ticker}{Style.RESET_ALL}]")
        print(
            tabulate(
                table_data,
                headers=[f"{Fore.WHITE}Agent", "Signal", "Confidence", "Reasoning"],
                tablefmt="grid",
                colalign=("left", "center", "right", "left"),
            )
        )

        # Print Trading Decision Table
        action = decision.get("action", "").upper()
        action_color = {
            "BUY": Fore.GREEN,
            "SELL": Fore.RED,
            "HOLD": Fore.YELLOW,
            "COVER": Fore.GREEN,
            "SHORT": Fore.RED,
        }.get(action, Fore.WHITE)

        # Get reasoning and format it
        raw_reasoning = decision.get("reasoning", "")
        wrapped_reasoning = textwrap.fill(_summarize_reasoning(raw_reasoning), width=60) if raw_reasoning else ""

        decision_data = [
            ["Action", f"{action_color}{action}{Style.RESET_ALL}"],
            [
                "Confidence",
                f"{Fore.WHITE}{decision.get('confidence'):.1f}%{Style.RESET_ALL}",
            ],
            ["Reasoning", f"{Fore.WHITE}{wrapped_reasoning}{Style.RESET_ALL}"],
        ]
        if decision.get("narrative"):
            decision_data.append(["Analysis", f"{Fore.CYAN}{textwrap.fill(decision['narrative'], width=72)}{Style.RESET_ALL}"])
        
        print(f"\n{Fore.WHITE}{Style.BRIGHT}TRADING DECISION:{Style.RESET_ALL} [{Fore.CYAN}{ticker}{Style.RESET_ALL}]")
        print(tabulate(decision_data, tablefmt="grid", colalign=("left", "left")))

    # Print Portfolio Summary
    print(f"\n{Fore.WHITE}{Style.BRIGHT}PORTFOLIO SUMMARY:{Style.RESET_ALL}")
    portfolio_data = []
    
    # Short display names for each agent
    analyst_signals = result.get("analyst_signals", {})
    for ticker, decision in decisions.items():
        action = decision.get("action", "").upper()
        action_color = {
            "BUY": Fore.GREEN, "SELL": Fore.RED, "HOLD": Fore.YELLOW,
            "COVER": Fore.GREEN, "SHORT": Fore.RED,
        }.get(action, Fore.WHITE)

        bullish_count = bearish_count = neutral_count = 0
        for agent, signals in analyst_signals.items():
            if "risk_management" in agent or agent in _NON_LLM_AGENTS or ticker not in signals:
                continue
            sig = signals[ticker].get("signal", "neutral").lower()
            if sig == "bullish":   bullish_count += 1
            elif sig == "bearish": bearish_count += 1
            else:                  neutral_count += 1

        # Build synthesis column from portfolio decision
        narrative = decision.get("narrative", "")
        synth_str = textwrap.fill(narrative, width=55) if narrative else "-"

        portfolio_data.append(
            [
                f"{Fore.CYAN}{ticker}{Style.RESET_ALL}",
                f"{action_color}{action}{Style.RESET_ALL}",
                f"{Fore.WHITE}{decision.get('confidence'):.1f}%{Style.RESET_ALL}",
                f"{Fore.GREEN}{bullish_count}{Style.RESET_ALL}",
                f"{Fore.RED}{bearish_count}{Style.RESET_ALL}",
                f"{Fore.YELLOW}{neutral_count}{Style.RESET_ALL}",
                synth_str,
            ]
        )

    headers = [
        f"{Fore.WHITE}Ticker",
        f"{Fore.WHITE}Action",
        f"{Fore.WHITE}Confidence",
        f"{Fore.WHITE}Bull",
        f"{Fore.WHITE}Bear",
        f"{Fore.WHITE}Neut",
        f"{Fore.WHITE}Synthesis",
    ]

    print(
        tabulate(
            portfolio_data,
            headers=headers,
            tablefmt="grid",
            colalign=("left", "center", "right", "center", "center", "center", "left"),
        )
    )


def print_backtest_results(table_rows: list) -> None:
    """Print the backtest results in a nicely formatted table"""
    # Clear the screen
    os.system("cls" if os.name == "nt" else "clear")

    # Split rows into ticker rows and summary rows
    ticker_rows = []
    summary_rows = []

    for row in table_rows:
        if isinstance(row[1], str) and "PORTFOLIO SUMMARY" in row[1]:
            summary_rows.append(row)
        else:
            ticker_rows.append(row)

    # Display latest portfolio summary
    if summary_rows:
        # Pick the most recent summary by date (YYYY-MM-DD)
        latest_summary = max(summary_rows, key=lambda r: r[0])
        print(f"\n{Fore.WHITE}{Style.BRIGHT}PORTFOLIO SUMMARY:{Style.RESET_ALL}")

        # Adjusted indexes after adding Long/Short Shares
        position_str = latest_summary[7].split("$")[1].split(Style.RESET_ALL)[0].replace(",", "")
        cash_str     = latest_summary[8].split("$")[1].split(Style.RESET_ALL)[0].replace(",", "")
        total_str    = latest_summary[9].split("$")[1].split(Style.RESET_ALL)[0].replace(",", "")

        print(f"Cash Balance: {Fore.CYAN}${float(cash_str):,.2f}{Style.RESET_ALL}")
        print(f"Total Position Value: {Fore.YELLOW}${float(position_str):,.2f}{Style.RESET_ALL}")
        print(f"Total Value: {Fore.WHITE}${float(total_str):,.2f}{Style.RESET_ALL}")
        print(f"Portfolio Return: {latest_summary[10]}")
        if len(latest_summary) > 14 and latest_summary[14]:
            print(f"Benchmark Return: {latest_summary[14]}")

        # Display performance metrics if available
        if latest_summary[11]:  # Sharpe ratio
            print(f"Sharpe Ratio: {latest_summary[11]}")
        if latest_summary[12]:  # Sortino ratio
            print(f"Sortino Ratio: {latest_summary[12]}")
        if latest_summary[13]:  # Max drawdown
            print(f"Max Drawdown: {latest_summary[13]}")

    # Add vertical spacing
    print("\n" * 2)

    # Print the table with just ticker rows
    print(
        tabulate(
            ticker_rows,
            headers=[
                "Date",
                "Ticker",
                "Action",
                "Quantity",
                "Price",
                "Long Shares",
                "Short Shares",
                "Position Value",
            ],
            tablefmt="grid",
            colalign=(
                "left",    # Date
                "left",    # Ticker
                "center",  # Action
                "right",   # Quantity
                "right",   # Price
                "right",   # Long Shares
                "right",   # Short Shares
                "right",   # Position Value
            ),
        )
    )

    # Add vertical spacing
    print("\n" * 4)


def format_backtest_row(
    date: str,
    ticker: str,
    action: str,
    quantity: float,
    price: float,
    long_shares: float = 0,
    short_shares: float = 0,
    position_value: float = 0,
    is_summary: bool = False,
    total_value: float = None,
    return_pct: float = None,
    cash_balance: float = None,
    total_position_value: float = None,
    sharpe_ratio: float = None,
    sortino_ratio: float = None,
    max_drawdown: float = None,
    benchmark_return_pct: float | None = None,
) -> list[any]:
    """Format a row for the backtest results table"""
    # Color the action
    action_color = {
        "BUY": Fore.GREEN,
        "COVER": Fore.GREEN,
        "SELL": Fore.RED,
        "SHORT": Fore.RED,
        "HOLD": Fore.WHITE,
    }.get(action.upper(), Fore.WHITE)

    if is_summary:
        return_color = Fore.GREEN if return_pct >= 0 else Fore.RED
        benchmark_str = ""
        if benchmark_return_pct is not None:
            bench_color = Fore.GREEN if benchmark_return_pct >= 0 else Fore.RED
            benchmark_str = f"{bench_color}{benchmark_return_pct:+.2f}%{Style.RESET_ALL}"
        return [
            date,
            f"{Fore.WHITE}{Style.BRIGHT}PORTFOLIO SUMMARY{Style.RESET_ALL}",
            "",  # Action
            "",  # Quantity
            "",  # Price
            "",  # Long Shares
            "",  # Short Shares
            f"{Fore.YELLOW}${total_position_value:,.2f}{Style.RESET_ALL}",  # Total Position Value
            f"{Fore.CYAN}${cash_balance:,.2f}{Style.RESET_ALL}",  # Cash Balance
            f"{Fore.WHITE}${total_value:,.2f}{Style.RESET_ALL}",  # Total Value
            f"{return_color}{return_pct:+.2f}%{Style.RESET_ALL}",  # Return
            f"{Fore.YELLOW}{sharpe_ratio:.2f}{Style.RESET_ALL}" if sharpe_ratio is not None else "",  # Sharpe Ratio
            f"{Fore.YELLOW}{sortino_ratio:.2f}{Style.RESET_ALL}" if sortino_ratio is not None else "",  # Sortino Ratio
            f"{Fore.RED}{max_drawdown:.2f}%{Style.RESET_ALL}" if max_drawdown is not None else "",  # Max Drawdown (signed)
            benchmark_str,  # Benchmark (S&P 500)
        ]
    else:
        return [
            date,
            f"{Fore.CYAN}{ticker}{Style.RESET_ALL}",
            f"{action_color}{action.upper()}{Style.RESET_ALL}",
            f"{action_color}{quantity:,.0f}{Style.RESET_ALL}",
            f"{Fore.WHITE}{price:,.2f}{Style.RESET_ALL}",
            f"{Fore.GREEN}{long_shares:,.0f}{Style.RESET_ALL}",   # Long Shares
            f"{Fore.RED}{short_shares:,.0f}{Style.RESET_ALL}",    # Short Shares
            f"{Fore.YELLOW}{position_value:,.2f}{Style.RESET_ALL}",
        ]
