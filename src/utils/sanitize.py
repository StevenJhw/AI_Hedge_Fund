"""Post-process LLM portfolio decisions against raw signal counts.

Rules:
  - BUY / COVER  requires  bullish >= bearish
  - SELL / SHORT requires  bearish >= bullish
  - If the LLM's action contradicts the signal majority → override to HOLD
  - Confidence below 25% on a non-HOLD action → downgrade to HOLD
"""


def _count_signals(analyst_signals: dict, ticker: str) -> tuple[int, int, int]:
    """Return (bullish, bearish, neutral) counts for a ticker across all agents."""
    bullish = bearish = neutral = 0
    for agent_id, signals in analyst_signals.items():
        if "risk_management" in agent_id:
            continue
        sig = (signals.get(ticker) or {}).get("signal", "neutral")
        if sig == "bullish":
            bullish += 1
        elif sig == "bearish":
            bearish += 1
        else:
            neutral += 1
    return bullish, bearish, neutral


def sanitize_decisions(result: dict) -> dict:
    """Validate each portfolio decision against signal counts; override if inconsistent."""
    decisions      = (result.get("decisions") or {})
    analyst_signals = (result.get("analyst_signals") or {})

    for ticker, decision in decisions.items():
        action     = (decision.get("action") or "hold").lower()
        confidence = float(decision.get("confidence") or 0)

        bullish, bearish, neutral = _count_signals(analyst_signals, ticker)

        override = None

        # Low-confidence non-hold → HOLD
        if action != "hold" and confidence < 25:
            override = f"Low confidence ({confidence:.0f}%) overridden to HOLD"

        # BUY/COVER requires strict bullish majority
        elif action in ("buy", "cover") and bullish <= bearish:
            override = (f"Signal mismatch: {bullish}B/{bearish}Br "
                        f"but LLM said {action.upper()} — overridden to HOLD")

        # SELL/SHORT requires strict bearish majority
        elif action in ("sell", "short") and bearish <= bullish:
            override = (f"Signal mismatch: {bullish}B/{bearish}Br "
                        f"but LLM said {action.upper()} — overridden to HOLD")

        if override:
            print(f"  [OVERRIDE] {ticker}: {override}")
            decision["action"]     = "hold"
            decision["quantity"]   = 0
            decision["confidence"] = 0
            decision["reasoning"]  = override

    return result
