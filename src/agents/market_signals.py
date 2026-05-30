"""Market signals analyst — short interest, options put/call ratio, analyst ratings."""

import json
from langchain_core.messages import HumanMessage
from src.graph.state import AgentState, show_agent_reasoning
from src.utils.progress import progress
from src.tools.api import get_short_interest, get_options_sentiment, get_analyst_ratings


def market_signals_analyst_agent(state: AgentState, agent_id: str = "market_signals_analyst_agent"):
    data    = state.get("data", {})
    tickers = data.get("tickers", [])

    analysis = {}

    for ticker in tickers:
        progress.update_status(agent_id, ticker, "Fetching short interest")
        short = get_short_interest(ticker)

        progress.update_status(agent_id, ticker, "Fetching options data")
        opts = get_options_sentiment(ticker)

        progress.update_status(agent_id, ticker, "Fetching analyst ratings")
        ratings = get_analyst_ratings(ticker)

        signals: list[str] = []
        parts:   list[str] = []

        # ── 1. Analyst ratings ─────────────────────────────────────────────────
        bull_r = ratings.get("strong_buy", 0) + ratings.get("buy", 0)
        bear_r = ratings.get("sell", 0) + ratings.get("strong_sell", 0)
        hold_r = ratings.get("hold", 0)
        total_r = bull_r + bear_r + hold_r

        if total_r > 0:
            bull_pct = bull_r / total_r
            signals.append("bullish" if bull_pct >= 0.6 else "bearish" if bull_pct <= 0.3 else "neutral")
            parts.append(f"Analyst ratings: {bull_r} buy / {hold_r} hold / {bear_r} sell ({bull_pct*100:.0f}% bullish)")

        current = ratings.get("price_target_current")
        mean_pt = ratings.get("price_target_mean")
        if current and mean_pt and current > 0:
            upside = (mean_pt - current) / current * 100
            parts.append(f"Consensus price target: ${mean_pt:.2f} ({upside:+.1f}% upside)")

        # ── 2. Options put/call ratio ──────────────────────────────────────────
        pcr = opts.get("put_call_ratio_oi")
        iv  = opts.get("avg_iv_pct")
        if pcr is not None:
            signals.append("bullish" if pcr < 0.7 else "bearish" if pcr > 1.3 else "neutral")
            parts.append(f"Put/call ratio (OI): {pcr:.2f} — {'bullish (calls dominate)' if pcr < 0.7 else 'bearish (puts dominate)' if pcr > 1.3 else 'neutral'}")
        if iv is not None:
            parts.append(f"Avg implied volatility: {iv:.1f}%")

        # ── 3. Short interest ──────────────────────────────────────────────────
        short_pct   = short.get("short_percent_of_float")
        short_ratio = short.get("short_ratio")
        if short_pct is not None:
            signals.append("bearish" if short_pct > 0.15 else "bullish" if short_pct < 0.05 else "neutral")
            ratio_str = f", {short_ratio:.1f} days to cover" if short_ratio else ""
            parts.append(f"Short interest: {short_pct*100:.1f}% of float{ratio_str}")

        # ── Aggregate ──────────────────────────────────────────────────────────
        if not signals:
            analysis[ticker] = {
                "signal": "neutral", "confidence": 0,
                "reasoning": "Insufficient market signals data",
            }
            progress.update_status(agent_id, ticker, "Done", analysis="Insufficient data")
            continue

        bull = signals.count("bullish")
        bear = signals.count("bearish")
        total = len(signals)

        if bull > bear:
            signal, conf = "bullish", round(bull / total * 100)
        elif bear > bull:
            signal, conf = "bearish", round(bear / total * 100)
        else:
            signal, conf = "neutral", 50

        analysis[ticker] = {
            "signal":     signal,
            "confidence": conf,
            "reasoning":  " | ".join(parts) if parts else "No data",
        }
        progress.update_status(agent_id, ticker, "Done")

    message = HumanMessage(content=json.dumps(analysis), name=agent_id)

    if state["metadata"]["show_reasoning"]:
        show_agent_reasoning(analysis, "Market Signals Analyst")

    state["data"]["analyst_signals"][agent_id] = analysis
    progress.update_status(agent_id, None, "Done")
    return {"messages": [message], "data": data}
