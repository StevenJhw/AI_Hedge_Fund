"""Helper to extract data-agent signals from state for use in investor agent prompts."""
import json

_DATA_AGENTS = {
    "fundamentals_analyst_agent":   "Fundamentals",
    "technical_analyst_agent":      "Technicals",
    "sentiment_analyst_agent":      "Sentiment & News",
    "valuation_analyst_agent":      "Valuation",
    "market_signals_analyst_agent": "Market Signals",
    "macro_analyst_agent":          "Macro (Yield Curve)",
    "earnings_analyst_agent":       "Earnings",
    "industry_analyst_agent":       "Industry & Sector",
}


def get_data_context(state: dict, ticker: str) -> str:
    """Return formatted data-agent signals for a ticker, or '' if none available."""
    analyst_signals = (state.get("data") or {}).get("analyst_signals", {})
    lines = []
    for agent_id, display in _DATA_AGENTS.items():
        sigs = analyst_signals.get(agent_id, {})
        if ticker not in sigs:
            continue
        s      = sigs[ticker]
        signal = s.get("signal", "neutral")
        conf   = s.get("confidence", 0)
        reas   = s.get("reasoning", "")
        if isinstance(reas, dict):
            reas = json.dumps(reas, separators=(",", ":"))
        lines.append(f"  {display}: {signal} ({conf:.0f}%) — {str(reas)[:200]}")

    if not lines:
        return ""
    return "DATA_CONTEXT (computed signals — use as supporting evidence):\n" + "\n".join(lines)
