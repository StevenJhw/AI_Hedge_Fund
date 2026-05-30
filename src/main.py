import sys

from dotenv import load_dotenv
from langchain_core.messages import HumanMessage
from langgraph.graph import END, StateGraph
from colorama import Fore, Style, init
import questionary
from src.agents.portfolio_manager import portfolio_management_agent
from src.agents.risk_manager import risk_management_agent
from src.data.prefetch import data_prefetch_agent
from src.graph.state import AgentState
from src.utils.display import print_trading_output
from src.utils.analysts import ANALYST_ORDER, get_analyst_nodes
from src.utils.progress import progress
from src.utils.visualize import save_graph_as_png
from src.cli.input import (
    parse_cli_inputs,
)

import argparse
from datetime import datetime
from dateutil.relativedelta import relativedelta
import json

# Load environment variables from .env file
load_dotenv()

init(autoreset=True)


def parse_hedge_fund_response(response):
    """Parses a JSON string and returns a dictionary."""
    try:
        return json.loads(response)
    except json.JSONDecodeError as e:
        print(f"JSON decoding error: {e}\nResponse: {repr(response)}")
        return None
    except TypeError as e:
        print(f"Invalid response type (expected string, got {type(response).__name__}): {e}")
        return None
    except Exception as e:
        print(f"Unexpected error while parsing response: {e}\nResponse: {repr(response)}")
        return None


##### Run the Hedge Fund #####
def run_hedge_fund(
    tickers: list[str],
    start_date: str,
    end_date: str,
    portfolio: dict,
    show_reasoning: bool = False,
    selected_analysts: list[str] = [],
    model_name: str = "gpt-4.1",
    model_provider: str = "OpenAI",
):
    # Start progress tracking
    progress.start()

    try:
        # Build workflow (default to all analysts when none provided)
        workflow = create_workflow(selected_analysts if selected_analysts else None)
        agent = workflow.compile()

        final_state = agent.invoke(
            {
                "messages": [
                    HumanMessage(
                        content="Make trading decisions based on the provided data.",
                    )
                ],
                "data": {
                    "tickers": tickers,
                    "portfolio": portfolio,
                    "start_date": start_date,
                    "end_date": end_date,
                    "analyst_signals": {},
                },
                "metadata": {
                    "show_reasoning": show_reasoning,
                    "model_name": model_name,
                    "model_provider": model_provider,
                },
            },
        )

        return {
            "decisions": parse_hedge_fund_response(final_state["messages"][-1].content),
            "analyst_signals": final_state["data"]["analyst_signals"],
        }
    finally:
        # Stop progress tracking
        progress.stop()


_DATA_AGENTS = {
    "fundamentals_analyst", "technical_analyst", "sentiment_analyst", "valuation_analyst",
    "market_signals_analyst", "macro_analyst", "earnings_analyst", "industry_analyst",
}


def start(state: AgentState):
    """Initialize the workflow with the input message."""
    return state


MIN_AGENTS_WITH_DATA = 2  # 一只股票至少要有这么多个数据Agent给出 confidence>0 才算"数据充足"


def _data_sync(state: AgentState):
    """
    数据质量关卡：按股票粒度过滤。
    - 数据充足的股票 → 保留在 tickers 列表，继续走 LLM 分析
    - 数据不足的股票 → 从 tickers 移除，直接标记结果，不再花 token
    """
    data = state["data"]
    analyst_signals = data.get("analyst_signals", {})
    tickers = data.get("tickers", [])

    sufficient_tickers = []
    insufficient_tickers = []

    for ticker in tickers:
        agents_with_data = 0
        for agent_id, signals_by_ticker in analyst_signals.items():
            if not isinstance(signals_by_ticker, dict):
                continue
            sig = signals_by_ticker.get(ticker)
            if isinstance(sig, dict) and sig.get("confidence", 0) > 0:
                agents_with_data += 1

        if agents_with_data >= MIN_AGENTS_WITH_DATA:
            sufficient_tickers.append(ticker)
        else:
            insufficient_tickers.append(ticker)

    # 对数据不足的股票，直接写入最终信号，后面的 LLM Agent 不会再处理它们
    if insufficient_tickers:
        msg_parts = []
        for ticker in insufficient_tickers:
            coverage = []
            for agent_id, signals_by_ticker in analyst_signals.items():
                if isinstance(signals_by_ticker, dict) and ticker in signals_by_ticker:
                    sig = signals_by_ticker[ticker]
                    conf = sig.get("confidence", 0) if isinstance(sig, dict) else 0
                    coverage.append(f"{agent_id}={conf}")
            msg_parts.append(f"  {ticker}: {', '.join(coverage) if coverage else 'no data'}")

        print(f"\n{Fore.YELLOW}⚠️  数据不足，以下股票跳过 LLM 分析（节省 token）：")
        print("\n".join(msg_parts))
        print(f"  建议: 检查代码是否正确，或调整日期范围。{Style.RESET_ALL}\n")

    # 只把数据充足的股票传给后面的 LLM Agent
    data["tickers"] = sufficient_tickers
    data["skipped_tickers"] = insufficient_tickers

    return {"data": data}


def _check_data_sufficiency(state: AgentState) -> str:
    """如果过滤后没有任何股票剩余，直接结束；否则继续。"""
    if not state["data"].get("tickers"):
        return "insufficient"
    return "sufficient"


def _data_insufficient_exit(state: AgentState):
    """所有股票数据都不足时的终止节点。"""
    skipped = state["data"].get("skipped_tickers", [])
    result = {
        "error": "insufficient_data",
        "message": "所有股票数据不足，无法进行 LLM 分析",
        "skipped_tickers": skipped,
    }

    from langchain_core.messages import AIMessage
    return {
        "messages": [AIMessage(content=json.dumps(result))],
        "data": state["data"],
    }


def _data_gate(state: AgentState):
    """Pass-through node after data sufficiency check passes."""
    return state


def create_workflow(selected_analysts=None):
    """Create the workflow with two-phase execution: data agents → LLM investor agents."""
    workflow = StateGraph(AgentState)
    workflow.add_node("start_node", start)
    workflow.add_node("data_sync_node", _data_sync)
    workflow.add_node("data_gate", _data_gate)
    workflow.add_node("data_insufficient_exit", _data_insufficient_exit)

    analyst_nodes = get_analyst_nodes()

    if selected_analysts is None:
        selected_analysts = list(analyst_nodes.keys())

    data_keys = [k for k in selected_analysts if k in _DATA_AGENTS]
    llm_keys  = [k for k in selected_analysts if k not in _DATA_AGENTS]

    # Phase 1: data agents + prefetch (start_node → agents → data_sync_node)
    # prefetch 和数据 Agent 并行跑，为 LLM Agent 预加载全部原始数据
    workflow.add_node("data_prefetch_agent", data_prefetch_agent)
    workflow.add_edge("start_node", "data_prefetch_agent")
    workflow.add_edge("data_prefetch_agent", "data_sync_node")

    if data_keys:
        for key in data_keys:
            node_name, node_func = analyst_nodes[key]
            workflow.add_node(node_name, node_func)
            workflow.add_edge("start_node", node_name)
            workflow.add_edge(node_name, "data_sync_node")
    else:
        workflow.add_edge("start_node", "data_sync_node")

    # 条件边：数据充分 → data_gate → LLM agents；数据不足 → 直接退出
    workflow.add_conditional_edges(
        "data_sync_node",
        _check_data_sufficiency,
        {
            "sufficient": "data_gate",
            "insufficient": "data_insufficient_exit",
        },
    )

    # Always add risk and portfolio management
    workflow.add_node("risk_management_agent", risk_management_agent)
    workflow.add_node("portfolio_manager", portfolio_management_agent)

    # Phase 2: LLM investor agents (data_gate → agent → risk_management_agent)
    if llm_keys:
        for key in llm_keys:
            node_name, node_func = analyst_nodes[key]
            workflow.add_node(node_name, node_func)
            workflow.add_edge("data_gate", node_name)
            workflow.add_edge(node_name, "risk_management_agent")
    else:
        workflow.add_edge("data_gate", "risk_management_agent")

    workflow.add_edge("risk_management_agent", "portfolio_manager")
    workflow.add_edge("portfolio_manager", END)
    workflow.add_edge("data_insufficient_exit", END)

    workflow.set_entry_point("start_node")
    return workflow


if __name__ == "__main__":
    inputs = parse_cli_inputs(
        description="Run the hedge fund trading system",
        require_tickers=True,
        default_months_back=None,
        include_graph_flag=True,
        include_reasoning_flag=True,
    )

    tickers = inputs.tickers
    selected_analysts = inputs.selected_analysts

    # Construct portfolio here
    portfolio = {
        "cash": inputs.initial_cash,
        "margin_requirement": inputs.margin_requirement,
        "margin_used": 0.0,
        "positions": {
            ticker: {
                "long": 0,
                "short": 0,
                "long_cost_basis": 0.0,
                "short_cost_basis": 0.0,
                "short_margin_used": 0.0,
            }
            for ticker in tickers
        },
        "realized_gains": {
            ticker: {
                "long": 0.0,
                "short": 0.0,
            }
            for ticker in tickers
        },
    }

    result = run_hedge_fund(
        tickers=tickers,
        start_date=inputs.start_date,
        end_date=inputs.end_date,
        portfolio=portfolio,
        show_reasoning=inputs.show_reasoning,
        selected_analysts=inputs.selected_analysts,
        model_name=inputs.model_name,
        model_provider=inputs.model_provider,
    )
    print_trading_output(result)
