"""Macro analyst — US Treasury yield curve and rate environment."""

import json
from langchain_core.messages import HumanMessage
from src.graph.state import AgentState, show_agent_reasoning
from src.utils.progress import progress
from src.tools.api import get_treasury_yields


def macro_analyst_agent(state: AgentState, agent_id: str = "macro_analyst_agent"):
    data    = state.get("data", {})
    tickers = data.get("tickers", [])

    progress.update_status(agent_id, None, "Fetching treasury yields")
    yields = get_treasury_yields()

    y3m    = yields.get("3m")
    y5y    = yields.get("5y")
    y10y   = yields.get("10y")
    y30y   = yields.get("30y")
    spread = yields.get("spread_10y_3m")

    # ── Yield curve signal ─────────────────────────────────────────────────────
    if spread is not None:
        if spread < -0.5:
            signal = "bearish"
            conf   = 75
            curve_desc = f"Deeply inverted ({spread:+.2f}%) — elevated recession risk"
        elif spread < 0:
            signal = "bearish"
            conf   = 60
            curve_desc = f"Inverted ({spread:+.2f}%) — mild recession caution"
        elif spread < 1.0:
            signal = "neutral"
            conf   = 50
            curve_desc = f"Flat/normal curve ({spread:+.2f}%) — neutral macro"
        else:
            signal = "bullish"
            conf   = 65
            curve_desc = f"Steep curve ({spread:+.2f}%) — growth-supportive environment"
    else:
        signal, conf, curve_desc = "neutral", 0, "Yield curve data unavailable"

    y_str = " | ".join(
        f"{k}={v}%" for k, v in [("3M", y3m), ("5Y", y5y), ("10Y", y10y), ("30Y", y30y)] if v is not None
    )
    reasoning = f"Yields: {y_str}. {curve_desc}"

    analysis = {
        ticker: {"signal": signal, "confidence": conf, "reasoning": reasoning}
        for ticker in tickers
    }

    for ticker in tickers:
        progress.update_status(agent_id, ticker, "Done")

    message = HumanMessage(content=json.dumps(analysis), name=agent_id)

    if state["metadata"]["show_reasoning"]:
        show_agent_reasoning(analysis, "Macro Analyst")

    state["data"]["analyst_signals"][agent_id] = analysis
    progress.update_status(agent_id, None, "Done")
    return {"messages": [message], "data": data}
