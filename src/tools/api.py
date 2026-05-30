"""Financial data via yfinance — no paid API key required."""

import logging
import warnings
import pandas as pd
import yfinance as yf

# suppress yfinance 404 noise for ETFs / tickers without fundamentals
logging.getLogger("yfinance").setLevel(logging.CRITICAL)
warnings.filterwarnings("ignore", category=FutureWarning)

from src.data.cache import get_cache
from src.data.models import (
    CompanyNews,
    FinancialMetrics,
    InsiderTrade,
    LineItem,
    Price,
)

logger = logging.getLogger(__name__)
_cache = get_cache()

# ── helpers ───────────────────────────────────────────────────────────────────

def _safe(val) -> float | None:
    try:
        if val is None:
            return None
        f = float(val)
        return None if f != f else f  # NaN → None
    except Exception:
        return None


def _get_cell(df: pd.DataFrame, candidates: list[str], col_idx: int) -> float | None:
    if df.empty or df.shape[1] <= col_idx:
        return None
    for name in candidates:
        if name in df.index:
            v = df.loc[name].iloc[col_idx]
            if pd.notna(v):
                return float(v)
    return None


def _filter_cols(df: pd.DataFrame, end_date: str) -> pd.DataFrame:
    if df.empty:
        return df
    cols = [c for c in df.columns if pd.Timestamp(c) <= pd.Timestamp(end_date)]
    return df[cols] if cols else df.iloc[:, :0]


# ── statement field maps ───────────────────────────────────────────────────────

_INCOME = {
    "revenue":                  ["Total Revenue"],
    "gross_profit":             ["Gross Profit"],
    "net_income":               ["Net Income", "Net Income Common Stockholders"],
    "operating_income":         ["Operating Income", "EBIT"],
    "ebitda":                   ["EBITDA", "Normalized EBITDA"],
    "interest_expense":         ["Interest Expense"],
    "income_tax_expense":       ["Tax Provision"],
    "research_and_development": ["Research And Development"],
}
_BALANCE = {
    "total_assets":        ["Total Assets"],
    "total_liabilities":   ["Total Liabilities Net Minority Interest", "Total Liabilities"],
    "shareholders_equity": ["Stockholders Equity", "Total Stockholders Equity", "Common Stock Equity"],
    "cash_and_equivalents":["Cash And Cash Equivalents", "Cash Cash Equivalents And Short Term Investments"],
    "total_debt":          ["Total Debt"],
    "current_assets":      ["Current Assets"],
    "current_liabilities": ["Current Liabilities"],
    "goodwill":            ["Goodwill"],
    "intangible_assets":   ["Goodwill And Other Intangible Assets"],
}
_CASH = {
    "capital_expenditure":                   ["Capital Expenditure"],
    "depreciation_and_amortization":         ["Depreciation And Amortization", "Reconciled Depreciation"],
    "free_cash_flow":                        ["Free Cash Flow"],
    "operating_cash_flow":                   ["Operating Cash Flow"],
    "dividends_and_other_cash_distributions":["Cash Dividends Paid", "Common Stock Dividend Paid"],
    "issuance_or_purchase_of_equity_shares": [
        "Repurchase Of Capital Stock", "Common Stock Repurchase", "Issuance Of Capital Stock",
    ],
}

# ── prices ────────────────────────────────────────────────────────────────────

def get_prices(ticker: str, start_date: str, end_date: str, api_key: str = None) -> list[Price]:
    cache_key = f"{ticker}_{start_date}_{end_date}"
    if cached := _cache.get_prices(cache_key):
        return [Price(**p) for p in cached]

    hist = yf.Ticker(ticker).history(start=start_date, end=end_date)
    if hist.empty:
        return []

    prices = [
        Price(
            open=round(float(row["Open"]), 4),
            close=round(float(row["Close"]), 4),
            high=round(float(row["High"]), 4),
            low=round(float(row["Low"]), 4),
            volume=int(row["Volume"]),
            time=ts.strftime("%Y-%m-%d"),
        )
        for ts, row in hist.iterrows()
    ]
    _cache.set_prices(cache_key, [p.model_dump() for p in prices])
    return prices


def prices_to_df(prices: list[Price]) -> pd.DataFrame:
    df = pd.DataFrame([p.model_dump() for p in prices])
    df["Date"] = pd.to_datetime(df["time"])
    df.set_index("Date", inplace=True)
    for col in ["open", "close", "high", "low", "volume"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df.sort_index(inplace=True)
    return df


def get_price_data(ticker: str, start_date: str, end_date: str, api_key: str = None) -> pd.DataFrame:
    return prices_to_df(get_prices(ticker, start_date, end_date))


# ── financial metrics ─────────────────────────────────────────────────────────

def get_financial_metrics(
    ticker: str,
    end_date: str,
    period: str = "ttm",
    limit: int = 10,
    api_key: str = None,
) -> list[FinancialMetrics]:
    cache_key = f"{ticker}_{period}_{end_date}_{limit}"
    if cached := _cache.get_financial_metrics(cache_key):
        return [FinancialMetrics(**m) for m in cached]

    t    = yf.Ticker(ticker)
    info = t.info or {}

    shares = _safe(info.get("sharesOutstanding"))
    fcf    = _safe(info.get("freeCashflow"))
    mkt    = _safe(info.get("marketCap"))

    # book value growth from two most-recent balance sheet periods
    bv_growth = None
    try:
        bs = _filter_cols(t.balance_sheet, end_date)
        if bs.shape[1] >= 2 and shares and shares > 0:
            eq_keys = ["Stockholders Equity", "Total Stockholders Equity", "Common Stock Equity"]
            eq0 = _get_cell(bs, eq_keys, 0)
            eq1 = _get_cell(bs, eq_keys, 1)
            if eq0 and eq1 and eq1 != 0:
                bv_growth = ((eq0 / shares) - (eq1 / shares)) / abs(eq1 / shares)
    except Exception:
        pass

    # yfinance returns debtToEquity as a percentage — divide by 100
    raw_dte = _safe(info.get("debtToEquity"))
    dte = raw_dte / 100 if raw_dte is not None else None

    m = FinancialMetrics(
        ticker=ticker,
        report_period=end_date,
        period=period,
        currency=info.get("currency", "USD"),
        market_cap=mkt,
        enterprise_value=_safe(info.get("enterpriseValue")),
        price_to_earnings_ratio=_safe(info.get("trailingPE")),
        price_to_book_ratio=_safe(info.get("priceToBook")),
        price_to_sales_ratio=_safe(info.get("priceToSalesTrailing12Months")),
        enterprise_value_to_ebitda_ratio=_safe(info.get("enterpriseToEbitda")),
        enterprise_value_to_revenue_ratio=_safe(info.get("enterpriseToRevenue")),
        free_cash_flow_yield=(fcf / mkt) if (fcf and mkt and mkt > 0) else None,
        peg_ratio=_safe(info.get("pegRatio")),
        gross_margin=_safe(info.get("grossMargins")),
        operating_margin=_safe(info.get("operatingMargins")),
        net_margin=_safe(info.get("profitMargins")),
        return_on_equity=_safe(info.get("returnOnEquity")),
        return_on_assets=_safe(info.get("returnOnAssets")),
        return_on_invested_capital=None,
        asset_turnover=None,
        inventory_turnover=None,
        receivables_turnover=None,
        days_sales_outstanding=None,
        operating_cycle=None,
        working_capital_turnover=None,
        current_ratio=_safe(info.get("currentRatio")),
        quick_ratio=_safe(info.get("quickRatio")),
        cash_ratio=None,
        operating_cash_flow_ratio=None,
        debt_to_equity=dte,
        debt_to_assets=None,
        interest_coverage=None,
        revenue_growth=_safe(info.get("revenueGrowth")),
        earnings_growth=_safe(info.get("earningsGrowth")),
        book_value_growth=bv_growth,
        earnings_per_share_growth=None,
        free_cash_flow_growth=None,
        operating_income_growth=None,
        ebitda_growth=None,
        payout_ratio=_safe(info.get("payoutRatio")),
        earnings_per_share=_safe(info.get("trailingEps")),
        book_value_per_share=_safe(info.get("bookValue")),
        free_cash_flow_per_share=(fcf / shares) if (fcf and shares and shares > 0) else None,
    )

    _cache.set_financial_metrics(cache_key, [m.model_dump()])
    return [m]


# ── line items ─────────────────────────────────────────────────────────────────

def search_line_items(
    ticker: str,
    line_items: list[str],
    end_date: str,
    period: str = "ttm",
    limit: int = 10,
    api_key: str = None,
) -> list[LineItem]:
    t    = yf.Ticker(ticker)
    info = t.info or {}

    inc = _filter_cols(t.income_stmt  if not t.income_stmt.empty  else pd.DataFrame(), end_date)
    bs  = _filter_cols(t.balance_sheet if not t.balance_sheet.empty else pd.DataFrame(), end_date)
    cf  = _filter_cols(t.cash_flow    if not t.cash_flow.empty    else pd.DataFrame(), end_date)

    n_periods = min(limit, max(
        inc.shape[1] if not inc.empty else 0,
        bs.shape[1]  if not bs.empty  else 0,
        cf.shape[1]  if not cf.empty  else 0,
        1,
    ))

    shares = _safe(info.get("sharesOutstanding"))

    results = []
    for i in range(n_periods):
        if not inc.empty and inc.shape[1] > i:
            report_date = inc.columns[i].strftime("%Y-%m-%d")
        elif not bs.empty and bs.shape[1] > i:
            report_date = bs.columns[i].strftime("%Y-%m-%d")
        else:
            report_date = end_date

        extra: dict = {}
        for item in line_items:
            if item == "outstanding_shares":
                extra[item] = shares
            elif item in _INCOME:
                extra[item] = _get_cell(inc, _INCOME[item], i)
            elif item in _BALANCE:
                extra[item] = _get_cell(bs, _BALANCE[item], i)
            elif item in _CASH:
                extra[item] = _get_cell(cf, _CASH[item], i)
            else:
                extra[item] = None

        results.append(LineItem(
            ticker=ticker,
            report_period=report_date,
            period=period,
            currency=info.get("currency", "USD"),
            **extra,
        ))

    return results


# ── insider trades ─────────────────────────────────────────────────────────────

def get_insider_trades(
    ticker: str,
    end_date: str,
    start_date: str | None = None,
    limit: int = 1000,
    api_key: str = None,
) -> list[InsiderTrade]:
    cache_key = f"{ticker}_{start_date or 'none'}_{end_date}_{limit}"
    if cached := _cache.get_insider_trades(cache_key):
        return [InsiderTrade(**tr) for tr in cached]

    try:
        df = yf.Ticker(ticker).insider_transactions
    except Exception:
        return []
    if df is None or df.empty:
        return []

    df = df.copy()
    if "Date" in df.columns:
        df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
        df = df[df["Date"] <= pd.Timestamp(end_date)]
        if start_date:
            df = df[df["Date"] >= pd.Timestamp(start_date)]

    trades = []
    for _, row in df.head(limit).iterrows():
        date_val = row.get("Date")
        filing_date = date_val.strftime("%Y-%m-%d") if pd.notna(date_val) else end_date

        shares_raw = _safe(row.get("Shares"))
        tx_type = str(row.get("Transaction", "")).lower()
        # sells → negative so sentiment agent reads them as bearish
        if shares_raw is not None and ("sale" in tx_type or "sell" in tx_type):
            shares_raw = -abs(shares_raw)

        trades.append(InsiderTrade(
            ticker=ticker,
            issuer=None,
            name=str(row.get("Insider", "")) or None,
            title=str(row.get("Position", "")) or None,
            is_board_director=None,
            transaction_date=filing_date,
            transaction_shares=shares_raw,
            transaction_price_per_share=None,
            transaction_value=_safe(row.get("Value")),
            shares_owned_before_transaction=None,
            shares_owned_after_transaction=None,
            security_title=None,
            filing_date=filing_date,
        ))

    _cache.set_insider_trades(cache_key, [tr.model_dump() for tr in trades])
    return trades


# ── company news ───────────────────────────────────────────────────────────────

_POS = {"surge", "beat", "growth", "strong", "record", "profit", "upgrade", "buy", "rally", "gain", "soar"}
_NEG = {"miss", "decline", "loss", "cut", "downgrade", "sell", "crash", "drop", "weak", "layoff", "warn"}


def _sentiment(title: str) -> str:
    tl = title.lower()
    pos = sum(1 for w in _POS if w in tl)
    neg = sum(1 for w in _NEG if w in tl)
    return "positive" if pos > neg else "negative" if neg > pos else "neutral"


def get_company_news(
    ticker: str,
    end_date: str,
    start_date: str | None = None,
    limit: int = 100,
    api_key: str = None,
) -> list[CompanyNews]:
    cache_key = f"{ticker}_{start_date or 'none'}_{end_date}_{limit}"
    if cached := _cache.get_company_news(cache_key):
        return [CompanyNews(**n) for n in cached]

    try:
        raw = yf.Ticker(ticker).news or []
    except Exception:
        return []

    # Add 1-day buffer so UTC-dated articles published on end_date still come through
    end_ts   = pd.Timestamp(end_date) + pd.Timedelta(days=1)
    start_ts = pd.Timestamp(start_date) if start_date else None

    news_list = []
    for item in raw:
        # yfinance ≥0.2.51 nests everything under item["content"]
        content = item.get("content") or item

        title   = content.get("title") or item.get("title", "")
        url     = (
            (content.get("canonicalUrl") or {}).get("url")
            or content.get("previewUrl")
            or item.get("link", "")
        )
        source  = (
            (content.get("provider") or {}).get("displayName")
            or item.get("publisher", "")
        )

        # pubDate is ISO-8601 in new format; providerPublishTime is Unix int in old
        pub_date = content.get("pubDate") or content.get("displayTime")
        pub_unix = item.get("providerPublishTime")
        if pub_date:
            dt = pd.Timestamp(pub_date)
        elif pub_unix:
            dt = pd.Timestamp(pub_unix, unit="s")
        else:
            dt = None

        if dt is not None:
            if dt.tz is not None:
                dt = dt.tz_localize(None)
            if dt > end_ts or (start_ts and dt < start_ts):
                continue
            date_str = dt.strftime("%Y-%m-%d")
        else:
            date_str = end_date

        news_list.append(CompanyNews(
            ticker=ticker,
            title=title,
            author=None,
            source=source,
            date=date_str,
            url=url,
            sentiment=_sentiment(title),
        ))
        if len(news_list) >= limit:
            break

    _cache.set_company_news(cache_key, [n.model_dump() for n in news_list])
    return news_list


def get_market_cap(ticker: str, end_date: str, api_key: str = None) -> float | None:
    return _safe((yf.Ticker(ticker).info or {}).get("marketCap"))


def get_short_interest(ticker: str) -> dict:
    """Short interest from yfinance info."""
    try:
        info = yf.Ticker(ticker).info or {}
        return {
            "short_percent_of_float": _safe(info.get("shortPercentOfFloat")),
            "short_ratio":            _safe(info.get("shortRatio")),
            "shares_short":           _safe(info.get("sharesShort")),
        }
    except Exception:
        return {}


def get_analyst_ratings(ticker: str) -> dict:
    """Analyst buy/hold/sell counts and consensus price target."""
    try:
        tk      = yf.Ticker(ticker)
        rec     = tk.recommendations
        targets = tk.analyst_price_targets or {}

        result = {
            "price_target_mean":    _safe(targets.get("mean")),
            "price_target_high":    _safe(targets.get("high")),
            "price_target_low":     _safe(targets.get("low")),
            "price_target_current": _safe(targets.get("current")),
        }

        if rec is not None and not rec.empty:
            row = rec.iloc[0]
            result.update({
                "strong_buy":  int(row.get("strongBuy",  0) or 0),
                "buy":         int(row.get("buy",        0) or 0),
                "hold":        int(row.get("hold",       0) or 0),
                "sell":        int(row.get("sell",       0) or 0),
                "strong_sell": int(row.get("strongSell", 0) or 0),
            })
        return result
    except Exception:
        return {}


def get_options_sentiment(ticker: str) -> dict:
    """Put/call ratio and avg implied volatility from the nearest 3 expiries."""
    try:
        tk      = yf.Ticker(ticker)
        expiries = tk.options
        if not expiries:
            return {}

        call_oi = put_oi = call_vol = put_vol = 0
        iv_vals: list[float] = []

        for exp in expiries[:3]:
            chain = tk.option_chain(exp)
            c, p  = chain.calls, chain.puts
            call_oi  += int(c["openInterest"].fillna(0).sum())
            put_oi   += int(p["openInterest"].fillna(0).sum())
            call_vol += int(c["volume"].fillna(0).sum())
            put_vol  += int(p["volume"].fillna(0).sum())
            iv_vals  += c["impliedVolatility"].dropna().tolist()
            iv_vals  += p["impliedVolatility"].dropna().tolist()

        return {
            "put_call_ratio_oi":     round(put_oi  / call_oi,  3) if call_oi  > 0 else None,
            "put_call_ratio_volume": round(put_vol / call_vol, 3) if call_vol > 0 else None,
            "avg_iv_pct":            round(sum(iv_vals) / len(iv_vals) * 100, 1) if iv_vals else None,
        }
    except Exception:
        return {}


def get_earnings_data(ticker: str) -> dict:
    """Earnings estimates, historical surprise rate, and next earnings date."""
    tk = yf.Ticker(ticker)
    result: dict = {}

    try:
        dates_df = tk.earnings_dates
        if dates_df is not None and not dates_df.empty:
            today = pd.Timestamp("today").normalize()
            future = dates_df[dates_df.index.tz_localize(None) > today]
            past   = dates_df[dates_df.index.tz_localize(None) <= today].dropna(subset=["Surprise(%)"])

            if not future.empty:
                next_dt = future.index[-1]
                if hasattr(next_dt, "tz_localize"):
                    next_dt = next_dt.tz_localize(None)
                result["next_earnings_date"] = str(next_dt.date())
                result["days_to_earnings"]   = (next_dt.date() - today.date()).days

            recent = past.head(8)
            if not recent.empty:
                beats = int((recent["Surprise(%)"] > 0).sum())
                result["beat_rate"]         = round(beats / len(recent) * 100)
                result["avg_surprise_pct"]  = round(float(recent["Surprise(%)"].mean()), 1)
                result["quarters_analyzed"] = len(recent)
    except Exception:
        pass

    try:
        ee = tk.earnings_estimate
        if ee is not None and not ee.empty:
            for period in ["0q", "+1q", "0y", "+1y"]:
                if period in ee.index:
                    result[f"eps_growth_{period.replace('+','')}"] = _safe(ee.loc[period, "growth"])
                    result[f"eps_avg_{period.replace('+','')}"]    = _safe(ee.loc[period, "avg"])
    except Exception:
        pass

    try:
        re = tk.revenue_estimate
        if re is not None and not re.empty:
            for period in ["0y", "+1y"]:
                if period in re.index:
                    result[f"rev_growth_{period.replace('+','')}"] = _safe(re.loc[period, "growth"])
    except Exception:
        pass

    return result


def get_company_profile(ticker: str) -> dict:
    """Sector, industry, business summary, beta, 52-week change."""
    try:
        info = yf.Ticker(ticker).info or {}
        summary = info.get("longBusinessSummary", "")
        return {
            "sector":   info.get("sector",   ""),
            "industry": info.get("industry", ""),
            "summary":  summary[:600] if summary else "",
            "beta":     _safe(info.get("beta")),
            "week52_change": _safe(info.get("52WeekChange")),
        }
    except Exception:
        return {}


def get_treasury_yields() -> dict:
    """Current US Treasury yields and 10Y-3M spread."""
    _SYMS = {"3m": "^IRX", "5y": "^FVX", "10y": "^TNX", "30y": "^TYX"}
    yields: dict[str, float | None] = {}
    for name, sym in _SYMS.items():
        try:
            hist = yf.Ticker(sym).history(period="5d")
            yields[name] = round(float(hist["Close"].iloc[-1]), 2) if not hist.empty else None
        except Exception:
            yields[name] = None

    y3m  = yields.get("3m")
    y10y = yields.get("10y")
    yields["spread_10y_3m"] = round(y10y - y3m, 2) if (y10y is not None and y3m is not None) else None
    return yields
