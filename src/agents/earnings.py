"""Earnings analyst — beat rate, forward EPS/revenue growth, upcoming catalyst."""

import json
from datetime import date
from langchain_core.messages import HumanMessage
from src.graph.state import AgentState, show_agent_reasoning
from src.utils.progress import progress
from src.tools.api import get_earnings_data


def earnings_analyst_agent(state: AgentState, agent_id: str = "earnings_analyst_agent"):
    data    = state.get("data", {})
    tickers = data.get("tickers", [])

    analysis = {}

    for ticker in tickers:
        progress.update_status(agent_id, ticker, "Fetching earnings data")
        ed = get_earnings_data(ticker)

        if not ed:
            analysis[ticker] = {
                "signal": "neutral", "confidence": 0,
                "reasoning": "No earnings data available (ETF or insufficient history)",
            }
            progress.update_status(agent_id, ticker, "Done", analysis="No data")
            continue

        signals: list[str] = []
        parts:   list[str] = []

        # ── 1. Historical beat rate ────────────────────────────────────────────
        beat_rate = ed.get("beat_rate")
        avg_surp  = ed.get("avg_surprise_pct")
        quarters  = ed.get("quarters_analyzed", 0)
        if beat_rate is not None:
            signals.append("bullish" if beat_rate >= 70 else "bearish" if beat_rate <= 40 else "neutral")
            parts.append(
                f"Beat rate: {beat_rate}% over last {quarters}Q "
                f"(avg surprise {avg_surp:+.1f}%)" if avg_surp is not None else
                f"Beat rate: {beat_rate}% over last {quarters}Q"
            )

        # ── 2. Forward EPS growth ──────────────────────────────────────────────
        growth_1y = ed.get("eps_growth_1y")
        growth_0y = ed.get("eps_growth_0y")
        if growth_1y is not None:
            pct = growth_1y * 100
            signals.append("bullish" if pct > 15 else "bearish" if pct < 0 else "neutral")
            parts.append(f"Forward EPS growth: {pct:+.1f}% (next 12 mo)")
        elif growth_0y is not None:
            pct = growth_0y * 100
            signals.append("bullish" if pct > 15 else "bearish" if pct < 0 else "neutral")
            parts.append(f"Current-year EPS growth: {pct:+.1f}%")

        # ── 3. Revenue growth ──────────────────────────────────────────────────
        rev_1y = ed.get("rev_growth_1y")
        if rev_1y is not None:
            parts.append(f"Revenue growth (next yr): {rev_1y*100:+.1f}%")

        # ── 4. Upcoming earnings catalyst ─────────────────────────────────────
        next_date = ed.get("next_earnings_date")
        days      = ed.get("days_to_earnings")
        if next_date:
            urgency = f" ← {days}d away" if days is not None and days <= 30 else ""
            parts.append(f"Next earnings: {next_date}{urgency}")

        # ── Aggregate ──────────────────────────────────────────────────────────
        if not signals:
            analysis[ticker] = {
                "signal": "neutral", "confidence": 0,
                "reasoning": " | ".join(parts) if parts else "Insufficient earnings data",
            }
            progress.update_status(agent_id, ticker, "Done")
            continue

        bull  = signals.count("bullish")
        bear  = signals.count("bearish")
        total = len(signals)

        if bull > bear:
            signal = "bullish"
            conf   = round(bull / total * 100)
            if avg_surp and avg_surp > 10:
                conf = min(conf + 10, 95)
        elif bear > bull:
            signal = "bearish"
            conf   = round(bear / total * 100)
        else:
            signal, conf = "neutral", 50

        analysis[ticker] = {
            "signal":     signal,
            "confidence": conf,
            "reasoning":  " | ".join(parts),
        }
        progress.update_status(agent_id, ticker, "Done")

    message = HumanMessage(content=json.dumps(analysis), name=agent_id)

    if state["metadata"]["show_reasoning"]:
        show_agent_reasoning(analysis, "Earnings Analyst")

    state["data"]["analyst_signals"][agent_id] = analysis
    progress.update_status(agent_id, None, "Done")
    return {"messages": [message], "data": data}
