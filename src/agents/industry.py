"""Industry analyst — sector momentum, AI/theme exposure, growth tailwinds (LLM-based)."""

import json
from langchain_core.messages import HumanMessage
from pydantic import BaseModel, Field
from src.graph.state import AgentState, show_agent_reasoning
from src.utils.progress import progress
from src.utils.llm import call_llm
from src.tools.api import get_company_profile


class IndustrySignal(BaseModel):
    signal:     str   = Field(default="neutral")
    confidence: float = Field(default=50.0)
    reasoning:  str   = Field(default="")


def industry_analyst_agent(state: AgentState, agent_id: str = "industry_analyst_agent"):
    data    = state.get("data", {})
    tickers = data.get("tickers", [])

    analysis = {}

    for ticker in tickers:
        progress.update_status(agent_id, ticker, "Fetching company profile")
        profile = get_company_profile(ticker)

        sector   = profile.get("sector",   "")
        industry = profile.get("industry", "")
        summary  = profile.get("summary",  "")
        beta     = profile.get("beta")
        w52chg   = profile.get("week52_change")

        if not sector and not industry and not summary:
            analysis[ticker] = {
                "signal": "neutral", "confidence": 0,
                "reasoning": "No company profile available (likely ETF or bond fund)",
            }
            progress.update_status(agent_id, ticker, "Done", analysis="No profile")
            continue

        progress.update_status(agent_id, ticker, "Analysing industry trends")

        context_parts = []
        if sector:   context_parts.append(f"Sector: {sector}")
        if industry: context_parts.append(f"Industry: {industry}")
        if beta is not None: context_parts.append(f"Beta: {beta:.2f}")
        if w52chg is not None: context_parts.append(f"52-week return: {w52chg*100:+.1f}%")
        if summary:  context_parts.append(f"Business: {summary}")

        prompt = (
            f"You are an industry analyst evaluating {ticker}.\n"
            f"{chr(10).join(context_parts)}\n\n"
            "Assess the industry and thematic outlook as of today:\n"
            "1. Is this sector experiencing strong tailwinds? (e.g. AI, cloud, energy transition, GLP-1, defence)\n"
            "2. What are the main growth drivers for this industry over the next 1-3 years?\n"
            "3. What are the key risks or headwinds?\n"
            "4. Overall: is the industry momentum bullish, bearish, or neutral for this stock?\n\n"
            "Return JSON only:\n"
            "{\n"
            '  "signal":     "bullish" | "bearish" | "neutral",\n'
            '  "confidence": <float 0-100>,\n'
            '  "reasoning":  "<2-3 sentences on industry momentum and key themes>"\n'
            "}"
        )

        result = call_llm(
            prompt,
            pydantic_model=IndustrySignal,
            agent_name=agent_id,
            state=state,
            default_factory=lambda: IndustrySignal(
                signal="neutral", confidence=0,
                reasoning="Industry analysis unavailable"
            ),
        )

        analysis[ticker] = {
            "signal":     result.signal,
            "confidence": result.confidence,
            "reasoning":  result.reasoning,
        }
        progress.update_status(agent_id, ticker, "Done")

    message = HumanMessage(content=json.dumps(analysis), name=agent_id)

    if state["metadata"]["show_reasoning"]:
        show_agent_reasoning(analysis, "Industry Analyst")

    state["data"]["analyst_signals"][agent_id] = analysis
    progress.update_status(agent_id, None, "Done")
    return {"messages": [message], "data": data}
