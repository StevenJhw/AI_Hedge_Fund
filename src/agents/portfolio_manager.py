import json
from langchain_core.messages import HumanMessage

from src.graph.state import AgentState, show_agent_reasoning
from pydantic import BaseModel, Field, field_validator
from typing_extensions import Literal
from src.utils.progress import progress
from src.utils.llm import call_llm
from src.utils.analysts import AGENT_HORIZON


class PortfolioDecision(BaseModel):
    action: Literal["buy", "sell", "short", "cover", "hold"]
    quantity: int = Field(description="Number of shares to trade")
    confidence: float = Field(description="Confidence 0-100")
    reasoning: str = Field(description="Reasoning for the decision")
    narrative: str = Field(default="", description="Comprehensive investment analysis narrative")

    @field_validator("confidence", mode="before")
    @classmethod
    def normalize_confidence(cls, v):
        if v is None:
            return 50.0
        try:
            v = float(v)
        except (TypeError, ValueError):
            return 50.0
        if v <= 1.0:
            return v * 100
        return max(0.0, min(100.0, v))


class SynthesisResult(BaseModel):
    confidence: float = Field(default=50.0, description="Final confidence 0-100")
    narrative:  str   = Field(default="", description="Comprehensive investment analysis narrative")


_FUND_AGENTS     = {"fundamentals_analyst_agent", "valuation_analyst_agent"}
_TECH_AGENTS     = {"technical_analyst_agent", "sentiment_analyst_agent"}
_EARNINGS_AGENTS = {"earnings_analyst_agent"}
_INDUSTRY_AGENTS = {"industry_analyst_agent"}

# These agents produce raw data/scores only — they don't cast a vote.
# Their signals are fed as context to the synthesis LLM but excluded from the buy/sell tally.
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

_AGENT_DISPLAY = {
    "warren_buffett_agent":        "Warren Buffett",
    "charlie_munger_agent":        "Charlie Munger",
    "ben_graham_agent":            "Ben Graham",
    "peter_lynch_agent":           "Peter Lynch",
    "phil_fisher_agent":           "Phil Fisher",
    "bill_ackman_agent":           "Bill Ackman",
    "cathie_wood_agent":           "Cathie Wood",
    "michael_burry_agent":         "Michael Burry",
    "mohnish_pabrai_agent":        "Mohnish Pabrai",
    "nassim_taleb_agent":          "Nassim Taleb",
    "stanley_druckenmiller_agent": "S. Druckenmiller",
    "rakesh_jhunjhunwala_agent":   "R. Jhunjhunwala",
    "aswath_damodaran_agent":      "A. Damodaran",
    "fundamentals_analyst_agent":    "Fundamentals",
    "technical_analyst_agent":       "Technicals",
    "sentiment_analyst_agent":       "Sentiment",
    "valuation_analyst_agent":       "Valuation",
    "market_signals_analyst_agent":  "Market Signals",
    "macro_analyst_agent":           "Macro",
    "earnings_analyst_agent":        "Earnings",
    "industry_analyst_agent":        "Industry",
}


def _agent_line(agent_id: str, data: dict) -> str:
    sig  = data.get("sig", "neutral")
    conf = data.get("conf", 50)
    reas = data.get("reasoning", "")
    if isinstance(reas, dict):
        reas = json.dumps(reas, separators=(",", ":"))
    name = _AGENT_DISPLAY.get(agent_id, agent_id.replace("_agent", "").replace("_", " ").title())
    return f"- {name}: {sig} {conf:.0f}% — {str(reas)[:120]}"




def synthesize_signals(
    ticker: str,
    agent_data: dict,
    state: dict,
    action: str = "hold",
    bullish_count: int = 0,
    bearish_count: int = 0,
    neutral_count: int = 0,
) -> SynthesisResult:
    """Ask the LLM to synthesize all analyst signals into a confidence score and comprehensive narrative."""
    fund_lines     = []
    tech_lines     = []
    earnings_lines = []
    industry_lines = []
    news_text      = ""
    short_lines    = []
    medium_lines   = []
    long_lines     = []

    for agent_id, data in agent_data.items():
        line = _agent_line(agent_id, data)
        if agent_id in _FUND_AGENTS:
            fund_lines.append(line)
        if agent_id in _TECH_AGENTS:
            tech_lines.append(line)
        if agent_id in _EARNINGS_AGENTS:
            earnings_lines.append(line)
        if agent_id in _INDUSTRY_AGENTS:
            industry_lines.append(line)
        if agent_id == "sentiment_analyst_agent":
            news_text = str(data.get("reasoning", ""))
        horizon = AGENT_HORIZON.get(agent_id)
        if horizon == "short":
            short_lines.append(line)
        elif horizon == "medium":
            medium_lines.append(line)
        elif horizon == "long":
            long_lines.append(line)

    def _block(lines):
        return "\n".join(lines) if lines else "  (no data)"

    total = bullish_count + bearish_count + neutral_count or 1

    prompt = (
        f"You are a senior portfolio manager writing an investment research note for {ticker}.\n"
        f"Recommended action: {action.upper()} "
        f"(LLM investor vote: {bullish_count} bullish / {bearish_count} bearish / {neutral_count} neutral "
        f"out of {total} LLM investors)\n\n"
        f"=== FUNDAMENTAL & VALUATION DATA ===\n{_block(fund_lines)}\n\n"
        f"=== TECHNICAL & SENTIMENT DATA ===\n{_block(tech_lines)}\n\n"
        f"=== RECENT NEWS & INSIDER TRADES ===\n{news_text or '  (no data)'}\n\n"
        f"=== EARNINGS DATA (beat rate, forward estimates, upcoming catalysts) ===\n{_block(earnings_lines)}\n\n"
        f"=== INDUSTRY & SECTOR THEMES (AI tailwinds, sector momentum, growth drivers) ===\n{_block(industry_lines)}\n\n"
        f"=== SHORT-TERM signals (days-weeks) ===\n{_block(short_lines)}\n\n"
        f"=== MEDIUM-TERM signals (months) ===\n{_block(medium_lines)}\n\n"
        f"=== LONG-TERM signals (1+ year) ===\n{_block(long_lines)}\n\n"
        "Based on ALL of the above, write a comprehensive investment research note covering:\n"
        "- Fundamental health: revenue growth, margins, balance sheet, valuation multiples\n"
        "- Technical picture: trend, momentum, key support/resistance\n"
        "- Recent news & catalysts and their likely price impact\n"
        "- Earnings quality: beat history, forward EPS/revenue growth, upcoming earnings risk\n"
        "- Industry & thematic tailwinds or headwinds (AI, sector cycle, macro)\n"
        "- Short-term outlook (days to weeks): immediate opportunities or risks\n"
        "- Long-term outlook (1+ year): structural advantages or concerns\n"
        "- Overall conviction: does the data strongly support the recommended action?\n\n"
        f"CRITICAL: Your narrative MUST support and explain the recommended {action.upper()} action. "
        "Never write text that contradicts or undermines that action. If opinions are mixed, "
        "acknowledge the disagreement but explain why the majority view prevails.\n\n"
        "Write 5-7 sentences of flowing, specific prose. Reference actual data points from the "
        "analysts above (e.g. specific ratios, signals, or reasoning). Do not use bullet points.\n\n"
        "Also set confidence (0-100) reflecting how strongly the combined data supports the action.\n\n"
        "Return JSON only:\n"
        "{\n"
        '  "confidence": <float 0-100>,\n'
        '  "narrative":  "<5-7 sentence comprehensive investment analysis>"\n'
        "}"
    )

    return call_llm(
        prompt,
        pydantic_model=SynthesisResult,
        agent_name="portfolio_manager",
        state=state,
        default_factory=SynthesisResult,
    )


class PortfolioManagerOutput(BaseModel):
    decisions: dict[str, PortfolioDecision] = Field(
        description="Dictionary of ticker to trading decisions"
    )


def portfolio_management_agent(state: AgentState, agent_id: str = "portfolio_manager"):
    """Makes final trading decisions by aggregating analyst signals deterministically."""
    portfolio       = state["data"]["portfolio"]
    analyst_signals = state["data"]["analyst_signals"]
    tickers         = state["data"]["tickers"]

    current_prices   = {}
    max_shares       = {}
    signals_by_ticker = {}

    for ticker in tickers:
        progress.update_status(agent_id, ticker, "Processing analyst signals")

        if agent_id.startswith("portfolio_manager_"):
            suffix          = agent_id.split("_")[-1]
            risk_manager_id = f"risk_management_agent_{suffix}"
        else:
            risk_manager_id = "risk_management_agent"

        risk_data              = analyst_signals.get(risk_manager_id, {}).get(ticker, {})
        remaining_limit        = float(risk_data.get("remaining_position_limit", 0.0))
        current_prices[ticker] = float(risk_data.get("current_price", 0.0))

        if current_prices[ticker] > 0:
            max_shares[ticker] = int(remaining_limit // current_prices[ticker])
        else:
            max_shares[ticker] = 0

        ticker_signals = {}
        for agent, signals in analyst_signals.items():
            if not agent.startswith("risk_management_agent") and ticker in signals:
                sig      = signals[ticker].get("signal")
                conf     = signals[ticker].get("confidence")
                reasoning = signals[ticker].get("reasoning", "")
                if sig is not None and conf is not None:
                    ticker_signals[agent] = {"sig": sig, "conf": conf, "reasoning": reasoning}
        signals_by_ticker[ticker] = ticker_signals

    state["data"]["current_prices"] = current_prices
    progress.update_status(agent_id, None, "Aggregating signals into decisions")

    result = generate_trading_decision(
        tickers=tickers,
        signals_by_ticker=signals_by_ticker,
        current_prices=current_prices,
        max_shares=max_shares,
        portfolio=portfolio,
    )

    # ── LLM synthesis: confidence + comprehensive narrative ──────────────────────
    for ticker in tickers:
        progress.update_status(agent_id, ticker, "Synthesizing signals")
        agents     = signals_by_ticker.get(ticker, {})
        dec        = result.decisions[ticker]
        # Only LLM agents count toward the vote header shown to the synthesis LLM
        llm_agents = {k: v for k, v in agents.items() if k not in _NON_LLM_AGENTS}
        bullish    = sum(1 for a in llm_agents.values() if a.get("sig") == "bullish")
        bearish    = sum(1 for a in llm_agents.values() if a.get("sig") == "bearish")
        neutral    = sum(1 for a in llm_agents.values() if a.get("sig") == "neutral")

        synth = synthesize_signals(
            ticker, agents, state,  # full agent data (incl. non-LLM) as context
            action=dec.action,
            bullish_count=bullish,
            bearish_count=bearish,
            neutral_count=neutral,
        )
        dec.confidence = synth.confidence
        dec.narrative  = synth.narrative

    message = HumanMessage(
        content=json.dumps(
            {t: d.model_dump() for t, d in result.decisions.items()}
        ),
        name=agent_id,
    )

    if state["metadata"]["show_reasoning"]:
        show_agent_reasoning(
            {t: d.model_dump() for t, d in result.decisions.items()},
            "Portfolio Manager",
        )

    progress.update_status(agent_id, None, "Done")

    return {
        "messages": state["messages"] + [message],
        "data":     state["data"],
    }


def compute_allowed_actions(
    tickers:       list[str],
    current_prices: dict[str, float],
    max_shares:    dict[str, int],
    portfolio:     dict,
) -> dict[str, dict[str, int]]:
    """Return {ticker: {action: max_qty}} constrained by cash, positions, and risk limits."""
    allowed  = {}
    cash     = float(portfolio.get("cash", 0.0))
    positions = portfolio.get("positions", {}) or {}
    margin_requirement = float(portfolio.get("margin_requirement", 0.5))
    margin_used        = float(portfolio.get("margin_used", 0.0))
    equity   = float(portfolio.get("equity", cash))

    for ticker in tickers:
        price         = float(current_prices.get(ticker, 0.0))
        pos           = positions.get(ticker, {})
        long_qty_raw  = float(pos.get("long",  0) or 0)
        short_qty_raw = float(pos.get("short", 0) or 0)
        long_shares   = int(round(long_qty_raw))   # fractional e.g. 0.43 → 0, 0.6 → 1
        # treat any meaningful fractional long as at least 1 share for sell purposes
        can_sell      = long_qty_raw >= 0.01
        short_shares  = int(round(short_qty_raw))
        max_qty       = int(max_shares.get(ticker, 0) or 0)

        pruned: dict[str, int] = {"hold": 0}

        # Sell existing longs (use rounded qty; min 1 so fractional positions can be exited)
        if can_sell:
            pruned["sell"] = max(long_shares, 1)

        # Buy up to risk limit and cash
        if cash > 0 and price > 0 and max_qty > 0:
            max_buy = min(max_qty, int(cash // price))
            if max_buy > 0:
                pruned["buy"] = max_buy

        # Cover existing shorts
        if short_shares > 0:
            pruned["cover"] = short_shares

        # Open short
        if price > 0 and max_qty > 0:
            if margin_requirement <= 0:
                max_short = max_qty
            else:
                avail_margin  = max(0.0, (equity / margin_requirement) - margin_used)
                max_short     = min(max_qty, int(avail_margin // price))
            if max_short > 0:
                pruned["short"] = max_short

        allowed[ticker] = pruned

    return allowed


def _avg_conf(agents: dict, side: str) -> float:
    """Average confidence of agents on the given side (bullish/bearish/neutral)."""
    vals = [
        float(a.get("conf") or a.get("confidence") or 50)
        for a in agents.values()
        if (a.get("sig") or a.get("signal")) == side
    ]
    return round(sum(vals) / len(vals)) if vals else 50.0


def generate_trading_decision(
    tickers:           list[str],
    signals_by_ticker: dict[str, dict],
    current_prices:    dict[str, float],
    max_shares:        dict[str, int],
    portfolio:         dict,
) -> PortfolioManagerOutput:
    """
    Aggregate analyst signals into decisions.

    Confidence  = average confidence of the agents on the winning side.
                  e.g. 4 bullish agents each 70% confident → final confidence 70%.
    Action rule = strict bullish majority → BUY (if capacity exists)
                  strict bearish majority → SELL (if holdings exist)
                  tie / no matching capacity → HOLD
    Quantity    = max_allowed × (majority_count / total_agents), scaled by conviction.
    """
    signal_only = portfolio.get("signal_only", False)

    if signal_only:
        # Pure signal mode: BUY / SELL / HOLD based solely on LLM investor votes.
        # Non-LLM agents (computational data) don't vote — they feed the synthesis LLM only.
        decisions: dict[str, PortfolioDecision] = {}
        for ticker in tickers:
            agents     = signals_by_ticker.get(ticker, {})
            llm_agents = {k: v for k, v in agents.items() if k not in _NON_LLM_AGENTS}
            bullish = sum(1 for a in llm_agents.values()
                          if (a.get("sig") or a.get("signal")) == "bullish")
            bearish = sum(1 for a in llm_agents.values()
                          if (a.get("sig") or a.get("signal")) == "bearish")
            neutral = sum(1 for a in llm_agents.values()
                          if (a.get("sig") or a.get("signal")) == "neutral")
            summary = f"{bullish}B/{bearish}Br/{neutral}N"

            if bullish > bearish:
                conf   = _avg_conf(llm_agents, "bullish")
                action = "buy"
                reason = f"Bullish majority ({summary}), avg conf {conf:.0f}%."
            elif bearish > bullish:
                conf   = _avg_conf(llm_agents, "bearish")
                action = "sell"
                reason = f"Bearish majority ({summary}), avg conf {conf:.0f}%."
            else:
                conf   = 50.0
                action = "hold"
                reason = f"No clear majority ({summary})."

            decisions[ticker] = PortfolioDecision(
                action=action, quantity=0, confidence=conf, reasoning=reason,
            )
        return PortfolioManagerOutput(decisions=decisions)

    # ── Portfolio mode: constrained by cash, holdings, risk limits ──────────────
    allowed_actions = compute_allowed_actions(tickers, current_prices, max_shares, portfolio)
    decisions: dict[str, PortfolioDecision] = {}

    for ticker in tickers:
        av         = allowed_actions.get(ticker, {"hold": 0})
        agents     = signals_by_ticker.get(ticker, {})
        llm_agents = {k: v for k, v in agents.items() if k not in _NON_LLM_AGENTS}

        bullish = sum(1 for a in llm_agents.values()
                      if (a.get("sig") or a.get("signal")) == "bullish")
        bearish = sum(1 for a in llm_agents.values()
                      if (a.get("sig") or a.get("signal")) == "bearish")
        neutral = sum(1 for a in llm_agents.values()
                      if (a.get("sig") or a.get("signal")) == "neutral")
        total   = max(bullish + bearish + neutral, 1)
        summary = f"{bullish}B/{bearish}Br/{neutral}N"

        if set(av.keys()) == {"hold"}:
            decisions[ticker] = PortfolioDecision(
                action="hold", quantity=0, confidence=100.0,
                reasoning=f"No trade capacity (risk limit hit or no price). Signals: {summary}",
            )

        elif bullish > bearish and "buy" in av:
            conf = _avg_conf(llm_agents, "bullish")
            qty  = max(1, round(av["buy"] * bullish / total))
            decisions[ticker] = PortfolioDecision(
                action="buy", quantity=qty, confidence=conf,
                reasoning=f"Bullish majority ({summary}), avg analyst conf {conf:.0f}%. "
                          f"Buy {qty} of {av['buy']} max shares.",
            )

        elif bearish > bullish and "sell" in av:
            conf = _avg_conf(llm_agents, "bearish")
            qty  = av["sell"]
            decisions[ticker] = PortfolioDecision(
                action="sell", quantity=qty, confidence=conf,
                reasoning=f"Bearish majority ({summary}), avg analyst conf {conf:.0f}%. "
                          f"Sell all {qty} shares.",
            )

        elif bearish > bullish and "short" in av:
            conf = _avg_conf(llm_agents, "bearish")
            qty  = max(1, round(av["short"] * bearish / total))
            decisions[ticker] = PortfolioDecision(
                action="short", quantity=qty, confidence=conf,
                reasoning=f"Bearish majority ({summary}), avg analyst conf {conf:.0f}%. "
                          f"Short {qty} of {av['short']} max shares.",
            )

        else:
            conf = _avg_conf(llm_agents, "neutral") if neutral >= max(bullish, bearish) else 50.0
            decisions[ticker] = PortfolioDecision(
                action="hold", quantity=0, confidence=conf,
                reasoning=f"No clear majority or matching action unavailable. {summary}",
            )

    return PortfolioManagerOutput(decisions=decisions)
