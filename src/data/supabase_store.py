"""
Supabase 持久化存储层。

替换内存缓存，数据存入 Supabase PostgreSQL。
- 写入：prefetch 拉完数据后存入
- 读取：下次请求先查 Supabase，未过期则直接用，不再调 yfinance
- 刷新策略：每种数据类型有不同的过期时间
"""

import os
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from supabase import create_client, Client

logger = logging.getLogger(__name__)

# 各数据类型的刷新间隔
REFRESH_INTERVALS = {
    "prices": timedelta(hours=16),         # 收盘后更新，盘中无意义
    "financials": timedelta(days=90),      # 季报才更新
    "metrics": timedelta(hours=16),        # 依赖当日股价
    "news": timedelta(hours=6),            # 新闻时效性强
    "insider_trades": timedelta(days=3),   # SEC filing 有延迟
}


def _get_client() -> Optional[Client]:
    """获取 Supabase 客户端，未配置则返回 None（降级到内存缓存）。"""
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_SERVICE_KEY")
    if not url or not key:
        return None
    return create_client(url, key)


def _now() -> datetime:
    return datetime.now(timezone.utc)


class SupabaseStore:
    """Supabase 持久化存储，提供按 ticker 的读写接口。"""

    def __init__(self):
        self._client = _get_client()

    @property
    def available(self) -> bool:
        return self._client is not None

    # ══════════════════════════════════════════════════════════════════════
    # 数据新鲜度检查
    # ══════════════════════════════════════════════════════════════════════

    def is_fresh(self, ticker: str, data_type: str) -> bool:
        """检查某个 ticker 的某种数据是否还新鲜（未过期）。"""
        if not self._client:
            return False
        try:
            resp = self._client.table("data_freshness") \
                .select("next_fetch_after") \
                .eq("ticker", ticker) \
                .eq("data_type", data_type) \
                .maybe_single() \
                .execute()
            if not resp.data:
                return False
            next_fetch = datetime.fromisoformat(resp.data["next_fetch_after"])
            return _now() < next_fetch
        except Exception as e:
            logger.warning(f"data_freshness check failed: {e}")
            return False

    def _mark_fresh(self, ticker: str, data_type: str):
        """标记数据为最新。"""
        if not self._client:
            return
        interval = REFRESH_INTERVALS.get(data_type, timedelta(hours=16))
        now = _now()
        try:
            self._client.table("data_freshness").upsert({
                "ticker": ticker,
                "data_type": data_type,
                "last_fetched_at": now.isoformat(),
                "next_fetch_after": (now + interval).isoformat(),
                "fetch_status": "ok",
            }).execute()
        except Exception as e:
            logger.warning(f"data_freshness upsert failed: {e}")

    # ══════════════════════════════════════════════════════════════════════
    # Prices
    # ══════════════════════════════════════════════════════════════════════

    def get_prices(self, ticker: str, start_date: str, end_date: str) -> Optional[list[dict]]:
        """从 Supabase 读取价格数据。返回 None 表示无缓存/已过期。"""
        if not self._client or not self.is_fresh(ticker, "prices"):
            return None
        try:
            resp = self._client.table("prices") \
                .select("*") \
                .eq("ticker", ticker) \
                .gte("trade_date", start_date) \
                .lte("trade_date", end_date) \
                .order("trade_date") \
                .execute()
            if not resp.data:
                return None
            # 转换为项目 Price 模型格式
            return [
                {
                    "open": float(r["open"]),
                    "close": float(r["close"]),
                    "high": float(r["high"]),
                    "low": float(r["low"]),
                    "volume": int(r["volume"]),
                    "time": r["trade_date"],
                }
                for r in resp.data
            ]
        except Exception as e:
            logger.warning(f"get_prices from Supabase failed: {e}")
            return None

    def save_prices(self, ticker: str, prices: list[dict]):
        """存入价格数据。prices 是 Price.model_dump() 的列表。"""
        if not self._client or not prices:
            return
        rows = [
            {
                "ticker": ticker,
                "trade_date": p["time"],
                "open": p["open"],
                "high": p["high"],
                "low": p["low"],
                "close": p["close"],
                "volume": p["volume"],
            }
            for p in prices
        ]
        try:
            self._client.table("prices").upsert(rows).execute()
            self._mark_fresh(ticker, "prices")
        except Exception as e:
            logger.warning(f"save_prices failed: {e}")

    # ══════════════════════════════════════════════════════════════════════
    # Financial Metrics
    # ══════════════════════════════════════════════════════════════════════

    def get_metrics(self, ticker: str, end_date: str) -> Optional[list[dict]]:
        """读取 metrics_daily 最新快照。"""
        if not self._client or not self.is_fresh(ticker, "metrics"):
            return None
        try:
            resp = self._client.table("metrics_daily") \
                .select("*") \
                .eq("ticker", ticker) \
                .lte("snapshot_date", end_date) \
                .order("snapshot_date", desc=True) \
                .limit(1) \
                .execute()
            return resp.data if resp.data else None
        except Exception as e:
            logger.warning(f"get_metrics failed: {e}")
            return None

    def save_metrics(self, ticker: str, metrics_data: dict):
        """存入一条 metrics 快照。"""
        if not self._client:
            return
        row = {
            "ticker": ticker,
            "snapshot_date": metrics_data.get("report_period", _now().date().isoformat()),
            "market_cap": metrics_data.get("market_cap"),
            "pe_ratio": metrics_data.get("price_to_earnings_ratio"),
            "pb_ratio": metrics_data.get("price_to_book_ratio"),
            "ps_ratio": metrics_data.get("price_to_sales_ratio"),
            "ev_to_ebitda": metrics_data.get("enterprise_value_to_ebitda_ratio"),
            "roe": metrics_data.get("return_on_equity"),
            "gross_margin": metrics_data.get("gross_margin"),
            "net_margin": metrics_data.get("net_margin"),
            "operating_margin": metrics_data.get("operating_margin"),
            "debt_to_equity": metrics_data.get("debt_to_equity"),
            "current_ratio": metrics_data.get("current_ratio"),
            "revenue_growth": metrics_data.get("revenue_growth"),
            "earnings_growth": metrics_data.get("earnings_growth"),
            "free_cash_flow_yield": metrics_data.get("free_cash_flow_yield"),
            "book_value_growth": metrics_data.get("book_value_growth"),
            "earnings_per_share": metrics_data.get("earnings_per_share"),
            "peg_ratio": metrics_data.get("peg_ratio"),
        }
        try:
            self._client.table("metrics_daily").upsert(row).execute()
            self._mark_fresh(ticker, "metrics")
        except Exception as e:
            logger.warning(f"save_metrics failed: {e}")

    # ══════════════════════════════════════════════════════════════════════
    # Financials (Line Items)
    # ══════════════════════════════════════════════════════════════════════

    def get_financials(self, ticker: str) -> Optional[list[dict]]:
        """读取 financials 表的数据。"""
        if not self._client or not self.is_fresh(ticker, "financials"):
            return None
        try:
            resp = self._client.table("financials") \
                .select("*") \
                .eq("ticker", ticker) \
                .order("report_period", desc=True) \
                .limit(10) \
                .execute()
            return resp.data if resp.data else None
        except Exception as e:
            logger.warning(f"get_financials failed: {e}")
            return None

    def save_financials(self, ticker: str, line_items: list[dict]):
        """存入财报 line items。"""
        if not self._client or not line_items:
            return
        rows = []
        for item in line_items:
            rows.append({
                "ticker": ticker,
                "report_period": item.get("report_period"),
                "period_type": item.get("period", "annual"),
                "revenue": item.get("revenue"),
                "net_income": item.get("net_income"),
                "operating_income": item.get("operating_income"),
                "ebitda": item.get("ebitda"),
                "free_cash_flow": item.get("free_cash_flow"),
                "total_assets": item.get("total_assets"),
                "total_liabilities": item.get("total_liabilities"),
                "shareholders_equity": item.get("shareholders_equity"),
                "total_debt": item.get("total_debt"),
                "cash_and_equivalents": item.get("cash_and_equivalents"),
                "shares_outstanding": item.get("outstanding_shares"),
                "capital_expenditure": item.get("capital_expenditure"),
                "depreciation_and_amortization": item.get("depreciation_and_amortization"),
                "research_and_development": item.get("research_and_development"),
                "gross_profit": item.get("gross_profit"),
                "interest_expense": item.get("interest_expense"),
                "operating_expense": item.get("operating_expense"),
                "ebit": item.get("ebit"),
                "dividends_paid": item.get("dividends_and_other_cash_distributions"),
                "share_buybacks": item.get("issuance_or_purchase_of_equity_shares"),
            })
        try:
            self._client.table("financials").upsert(rows).execute()
            self._mark_fresh(ticker, "financials")
        except Exception as e:
            logger.warning(f"save_financials failed: {e}")

    # ══════════════════════════════════════════════════════════════════════
    # News
    # ══════════════════════════════════════════════════════════════════════

    def get_news(self, ticker: str, start_date: str, end_date: str) -> Optional[list[dict]]:
        """读取新闻。"""
        if not self._client or not self.is_fresh(ticker, "news"):
            return None
        try:
            resp = self._client.table("news") \
                .select("*") \
                .eq("ticker", ticker) \
                .gte("published_at", start_date) \
                .lte("published_at", end_date) \
                .order("published_at", desc=True) \
                .execute()
            if not resp.data:
                return None
            return [
                {
                    "ticker": r["ticker"],
                    "title": r["title"],
                    "author": None,
                    "source": r["source"],
                    "date": r["published_at"],
                    "url": r["url"],
                    "sentiment": r["sentiment"],
                }
                for r in resp.data
            ]
        except Exception as e:
            logger.warning(f"get_news failed: {e}")
            return None

    def save_news(self, ticker: str, news_list: list[dict]):
        """存入新闻。"""
        if not self._client or not news_list:
            return
        rows = [
            {
                "ticker": ticker,
                "title": n.get("title", ""),
                "source": n.get("source"),
                "url": n.get("url", ""),
                "published_at": n.get("date"),
                "sentiment": n.get("sentiment"),
            }
            for n in news_list
        ]
        try:
            self._client.table("news").upsert(rows, on_conflict="ticker,url").execute()
            self._mark_fresh(ticker, "news")
        except Exception as e:
            logger.warning(f"save_news failed: {e}")

    # ══════════════════════════════════════════════════════════════════════
    # Insider Trades
    # ══════════════════════════════════════════════════════════════════════

    def get_insider_trades(self, ticker: str, start_date: str, end_date: str) -> Optional[list[dict]]:
        """读取内幕交易。"""
        if not self._client or not self.is_fresh(ticker, "insider_trades"):
            return None
        try:
            resp = self._client.table("insider_trades") \
                .select("*") \
                .eq("ticker", ticker) \
                .gte("transaction_date", start_date) \
                .lte("transaction_date", end_date) \
                .order("transaction_date", desc=True) \
                .execute()
            if not resp.data:
                return None
            return [
                {
                    "ticker": r["ticker"],
                    "issuer": None,
                    "name": r["insider_name"],
                    "title": r["title"],
                    "is_board_director": None,
                    "transaction_date": r["transaction_date"],
                    "transaction_shares": float(r["shares"]) if r["shares"] else None,
                    "transaction_price_per_share": float(r["price_per_share"]) if r["price_per_share"] else None,
                    "transaction_value": float(r["total_value"]) if r["total_value"] else None,
                    "shares_owned_before_transaction": None,
                    "shares_owned_after_transaction": None,
                    "security_title": None,
                    "filing_date": r["transaction_date"],
                }
                for r in resp.data
            ]
        except Exception as e:
            logger.warning(f"get_insider_trades failed: {e}")
            return None

    def save_insider_trades(self, ticker: str, trades: list[dict]):
        """存入内幕交易。"""
        if not self._client or not trades:
            return
        rows = []
        for t in trades:
            shares = t.get("transaction_shares")
            rows.append({
                "ticker": ticker,
                "insider_name": t.get("name"),
                "title": t.get("title"),
                "transaction_date": t.get("transaction_date") or t.get("filing_date"),
                "transaction_type": "sell" if (shares and shares < 0) else "buy",
                "shares": shares,
                "price_per_share": t.get("transaction_price_per_share"),
                "total_value": t.get("transaction_value"),
            })
        try:
            self._client.table("insider_trades").upsert(
                rows, on_conflict="ticker,insider_name,transaction_date,shares"
            ).execute()
            self._mark_fresh(ticker, "insider_trades")
        except Exception as e:
            logger.warning(f"save_insider_trades failed: {e}")

    # ══════════════════════════════════════════════════════════════════════
    # LLM Signals (分析结果)
    # ══════════════════════════════════════════════════════════════════════

    def save_llm_signal(self, ticker: str, analysis_date: str, agent_id: str,
                        signal: str, confidence: float, reasoning: str,
                        model_used: str = None):
        """保存一条 LLM 分析信号。"""
        if not self._client:
            return
        try:
            self._client.table("llm_signals").insert({
                "ticker": ticker,
                "analysis_date": analysis_date,
                "agent_id": agent_id,
                "signal": signal,
                "confidence": confidence,
                "reasoning": reasoning,
                "model_used": model_used,
            }).execute()
        except Exception as e:
            logger.warning(f"save_llm_signal failed: {e}")

    def get_previous_signals(self, ticker: str, agent_id: str, limit: int = 3) -> list[dict]:
        """获取某个 Agent 对某只股票的历史信号（用于注入 prompt 做参考）。"""
        if not self._client:
            return []
        try:
            resp = self._client.table("llm_signals") \
                .select("analysis_date, signal, confidence, reasoning") \
                .eq("ticker", ticker) \
                .eq("agent_id", agent_id) \
                .order("analysis_date", desc=True) \
                .limit(limit) \
                .execute()
            return resp.data or []
        except Exception as e:
            logger.warning(f"get_previous_signals failed: {e}")
            return []

    # ══════════════════════════════════════════════════════════════════════
    # Data Signals (数据Agent结果)
    # ══════════════════════════════════════════════════════════════════════

    def save_data_signal(self, ticker: str, analysis_date: str, agent_id: str,
                         signal: str, confidence: float, reasoning):
        """保存数据 Agent 的信号。"""
        if not self._client:
            return
        import json
        try:
            self._client.table("data_signals").upsert({
                "ticker": ticker,
                "analysis_date": analysis_date,
                "agent_id": agent_id,
                "signal": signal,
                "confidence": confidence,
                "reasoning": json.dumps(reasoning) if isinstance(reasoning, dict) else reasoning,
            }).execute()
        except Exception as e:
            logger.warning(f"save_data_signal failed: {e}")

    # ══════════════════════════════════════════════════════════════════════
    # Decisions (最终交易决策)
    # ══════════════════════════════════════════════════════════════════════

    def save_decision(self, analysis_date: str, ticker: str, action: str,
                      quantity: int = None, reasoning: str = None):
        """保存最终交易决策。"""
        if not self._client:
            return
        try:
            self._client.table("decisions").insert({
                "analysis_date": analysis_date,
                "ticker": ticker,
                "action": action,
                "quantity": quantity,
                "reasoning": reasoning,
            }).execute()
        except Exception as e:
            logger.warning(f"save_decision failed: {e}")


# 全局单例
_store: Optional[SupabaseStore] = None


def get_store() -> SupabaseStore:
    """获取全局 Supabase store 实例。"""
    global _store
    if _store is None:
        _store = SupabaseStore()
    return _store
