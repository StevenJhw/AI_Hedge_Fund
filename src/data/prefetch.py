"""
统一数据预加载器。

流程：
  1. 先查 Supabase 缓存，数据新鲜则直接用
  2. 数据过期或不存在 → 调 yfinance 拉取
  3. 拉取后存入 Supabase（持久化）
  4. 所有数据存入 state["data"]["raw"] 供 LLM Agent 直接读取
"""

from datetime import datetime, timedelta
from langchain_core.messages import HumanMessage

from src.graph.state import AgentState
from src.tools.api import (
    get_company_news,
    get_financial_metrics,
    get_insider_trades,
    get_market_cap,
    get_prices,
    prices_to_df,
    search_line_items,
)
from src.data.supabase_store import get_store
from src.utils.api_key import get_api_key_from_state
from src.utils.progress import progress

# 所有 LLM Agent 用到的 line_items 合集
ALL_LINE_ITEMS = [
    # 收入表
    "revenue",
    "gross_profit",
    "net_income",
    "operating_income",
    "ebit",
    "ebitda",
    "earnings_per_share",
    "interest_expense",
    "research_and_development",
    "operating_expense",
    # 资产负债表
    "total_assets",
    "total_liabilities",
    "shareholders_equity",
    "total_debt",
    "cash_and_equivalents",
    "current_assets",
    "current_liabilities",
    "goodwill",
    "intangible_assets",
    "outstanding_shares",
    # 现金流
    "capital_expenditure",
    "depreciation_and_amortization",
    "free_cash_flow",
    "operating_cash_flow",
    "dividends_and_other_cash_distributions",
    "issuance_or_purchase_of_equity_shares",
    # 利润率
    "gross_margin",
    "operating_margin",
    "debt_to_equity",
]


def data_prefetch_agent(state: AgentState, agent_id: str = "data_prefetch_agent"):
    """
    一次性预加载所有原始数据：
    - Supabase 有新鲜缓存 → 直接读
    - 没有 → yfinance 拉取 → 存 Supabase → 存 state
    """
    data = state["data"]
    tickers = data["tickers"]
    start_date = data["start_date"]
    end_date = data["end_date"]
    api_key = get_api_key_from_state(state, "FINANCIAL_DATASETS_API_KEY")
    store = get_store()

    # 回看一年（用于 insider trades 和 news）
    lookback_start = (datetime.fromisoformat(end_date) - timedelta(days=365)).date().isoformat()

    raw = {}

    for ticker in tickers:
        progress.update_status(agent_id, ticker, "Prefetching all data")
        ticker_data = {}

        # ── 1. Prices ───────────────────────────────────────────────────────
        progress.update_status(agent_id, ticker, "Prices")
        cached_prices = store.get_prices(ticker, start_date, end_date) if store.available else None
        if cached_prices:
            from src.data.models import Price
            ticker_data["prices"] = [Price(**p) for p in cached_prices]
        else:
            prices = get_prices(ticker, start_date, end_date, api_key=api_key)
            ticker_data["prices"] = prices
            if prices and store.available:
                store.save_prices(ticker, [p.model_dump() for p in prices])

        ticker_data["prices_df"] = prices_to_df(ticker_data["prices"]) if ticker_data["prices"] else None

        # ── 2. Financial Metrics ────────────────────────────────────────────
        progress.update_status(agent_id, ticker, "Financial metrics")
        cached_metrics = store.get_metrics(ticker, end_date) if store.available else None
        if cached_metrics:
            ticker_data["financial_metrics"] = get_financial_metrics(
                ticker, end_date, period="ttm", limit=10, api_key=api_key
            )
        else:
            ticker_data["financial_metrics"] = get_financial_metrics(
                ticker, end_date, period="ttm", limit=10, api_key=api_key
            )
            if ticker_data["financial_metrics"] and store.available:
                store.save_metrics(ticker, ticker_data["financial_metrics"][0].model_dump())

        # ── 3. Line Items (Financial Statements) ───────────────────────────
        progress.update_status(agent_id, ticker, "Financial statements")
        cached_financials = store.get_financials(ticker) if store.available else None
        if cached_financials:
            ticker_data["line_items"] = search_line_items(
                ticker, ALL_LINE_ITEMS, end_date, period="annual", limit=10, api_key=api_key
            )
        else:
            ticker_data["line_items"] = search_line_items(
                ticker, ALL_LINE_ITEMS, end_date, period="annual", limit=10, api_key=api_key
            )
            if ticker_data["line_items"] and store.available:
                store.save_financials(ticker, [li.model_dump() for li in ticker_data["line_items"]])

        # ── 4. Market Cap ──────────────────────────────────────────────────
        progress.update_status(agent_id, ticker, "Market cap")
        ticker_data["market_cap"] = get_market_cap(ticker, end_date, api_key=api_key)

        # ── 5. Insider Trades ──────────────────────────────────────────────
        progress.update_status(agent_id, ticker, "Insider trades")
        cached_trades = store.get_insider_trades(ticker, lookback_start, end_date) if store.available else None
        if cached_trades:
            from src.data.models import InsiderTrade
            ticker_data["insider_trades"] = [InsiderTrade(**t) for t in cached_trades]
        else:
            trades = get_insider_trades(
                ticker, end_date=end_date, start_date=lookback_start, limit=1000, api_key=api_key
            )
            ticker_data["insider_trades"] = trades
            if trades and store.available:
                store.save_insider_trades(ticker, [t.model_dump() for t in trades])

        # ── 6. Company News ────────────────────────────────────────────────
        progress.update_status(agent_id, ticker, "Company news")
        cached_news = store.get_news(ticker, lookback_start, end_date) if store.available else None
        if cached_news:
            from src.data.models import CompanyNews
            ticker_data["company_news"] = [CompanyNews(**n) for n in cached_news]
        else:
            news = get_company_news(
                ticker, end_date=end_date, start_date=lookback_start, limit=100, api_key=api_key
            )
            ticker_data["company_news"] = news
            if news and store.available:
                store.save_news(ticker, [n.model_dump() for n in news])

        raw[ticker] = ticker_data
        progress.update_status(agent_id, ticker, "Done")

    data["raw"] = raw
    progress.update_status(agent_id, None, "Done")

    return {
        "messages": [HumanMessage(content="Data prefetch complete.", name=agent_id)],
        "data": data,
    }


def get_raw_data(state: AgentState, ticker: str) -> dict:
    """LLM Agent 用这个函数从 state 中读取预加载的原始数据。"""
    return state.get("data", {}).get("raw", {}).get(ticker, {})
