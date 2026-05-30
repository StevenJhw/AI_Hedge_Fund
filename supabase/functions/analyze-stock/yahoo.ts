import { Price, Metrics, Financials, NewsItem, InsiderTrade, StockData, CompanyProfile, AnalystRatings, MacroData, ShortInterest, OptionsData, EarningsData } from "./types.ts";

// Yahoo Finance 需要 cookie + crumb 认证
let _cookie = "";
let _crumb = "";
let _authPromise: Promise<void> | null = null;

async function ensureAuth(): Promise<void> {
  if (_crumb) return;
  if (_authPromise) return _authPromise;

  _authPromise = (async () => {
    const cookieResp = await fetch("https://fc.yahoo.com", { redirect: "manual" });
    const cookies = cookieResp.headers.getSetCookie();
    _cookie = cookies.map((c) => c.split(";")[0]).join("; ");

    const crumbResp = await fetch("https://query2.finance.yahoo.com/v1/test/getcrumb", {
      headers: { "User-Agent": "Mozilla/5.0", "Cookie": _cookie },
    });
    _crumb = await crumbResp.text();
  })();

  return _authPromise;
}

async function fetchYahoo(url: string): Promise<any> {
  await ensureAuth();
  const separator = url.includes("?") ? "&" : "?";
  const fullUrl = `${url}${separator}crumb=${encodeURIComponent(_crumb)}`;

  const resp = await fetch(fullUrl, {
    headers: { "User-Agent": "Mozilla/5.0", "Cookie": _cookie },
  });
  if (!resp.ok) return null;
  return resp.json();
}

export async function getPrices(ticker: string, startDate: string, endDate: string): Promise<Price[]> {
  const period1 = Math.floor(new Date(startDate).getTime() / 1000);
  const period2 = Math.floor(new Date(endDate).getTime() / 1000);
  const url = `https://query2.finance.yahoo.com/v8/finance/chart/${ticker}?period1=${period1}&period2=${period2}&interval=1d`;
  const data = await fetchYahoo(url);

  const result = data?.chart?.result?.[0];
  if (!result) return [];

  const timestamps = result.timestamp || [];
  const quote = result.indicators?.quote?.[0] || {};

  return timestamps.map((ts: number, i: number) => ({
    date: new Date(ts * 1000).toISOString().split("T")[0],
    open: +(quote.open?.[i] ?? 0).toFixed(4),
    high: +(quote.high?.[i] ?? 0).toFixed(4),
    low: +(quote.low?.[i] ?? 0).toFixed(4),
    close: +(quote.close?.[i] ?? 0).toFixed(4),
    volume: quote.volume?.[i] ?? 0,
  })).filter((p: Price) => p.close > 0);
}

export async function getQuoteSummary(ticker: string): Promise<any> {
  const modules = [
    "financialData",
    "defaultKeyStatistics",
    "summaryDetail",
    "assetProfile",
    "recommendationTrend",
    "majorHoldersBreakdown",
    "earningsHistory",
    "earningsTrend",
    "calendarEvents",
    "incomeStatementHistory",
    "incomeStatementHistoryQuarterly",
    "balanceSheetHistory",
    "cashflowStatementHistory",
    "insiderTransactions",
  ].join(",");
  const url = `https://query2.finance.yahoo.com/v10/finance/quoteSummary/${ticker}?modules=${modules}`;
  const data = await fetchYahoo(url);
  return data?.quoteSummary?.result?.[0] || null;
}

export function extractProfile(summary: any): CompanyProfile {
  const ap = summary?.assetProfile || {};
  return {
    sector: ap.sector || "",
    industry: ap.industry || "",
    employees: ap.fullTimeEmployees,
    summary: (ap.longBusinessSummary || "").substring(0, 500),
  };
}

export function extractAnalystRatings(summary: any): AnalystRatings {
  const trend = summary?.recommendationTrend?.trend?.[0] || {};
  const fd = summary?.financialData || {};
  return {
    buy: (trend.strongBuy || 0) + (trend.buy || 0),
    hold: trend.hold || 0,
    sell: (trend.sell || 0) + (trend.strongSell || 0),
    target_price_mean: fd.targetMeanPrice?.raw,
    target_price_high: fd.targetHighPrice?.raw,
    target_price_low: fd.targetLowPrice?.raw,
  };
}

export function extractExtraMetrics(summary: any): Record<string, number | undefined> {
  const ks = summary?.defaultKeyStatistics || {};
  const sd = summary?.summaryDetail || {};
  const mh = summary?.majorHoldersBreakdown || {};
  return {
    beta: ks.beta?.raw,
    week52_change: ks["52WeekChange"]?.raw,
    dividend_yield: sd.dividendYield?.raw,
    insiders_percent_held: mh.insidersPercentHeld?.raw,
    institutions_percent_held: mh.institutionsPercentHeld?.raw,
  };
}

export function extractShortInterest(summary: any): ShortInterest {
  const ks = summary?.defaultKeyStatistics || {};
  return {
    shares_short: ks.sharesShort?.raw || 0,
    short_ratio: ks.shortRatio?.raw || 0,
    short_percent_of_float: ks.shortPercentOfFloat?.raw || 0,
  };
}

export function extractEarnings(summary: any): EarningsData {
  const eh = summary?.earningsHistory?.history || [];
  const et = summary?.earningsTrend?.trend || [];
  const cal = summary?.calendarEvents?.earnings;

  const beats = eh.filter((e: any) => (e.surprisePercent?.raw || 0) > 0).length;
  const surprises = eh.map((e: any) => e.surprisePercent?.raw || 0).filter((v: number) => v !== 0);
  const avgSurprise = surprises.length ? surprises.reduce((a: number, b: number) => a + b, 0) / surprises.length : 0;

  const nextDate = cal?.earningsDate?.[0]?.fmt;

  // Forward estimates from earningsTrend
  let fwdEps0y: number | undefined;
  let fwdEps1y: number | undefined;
  let fwdRev0y: number | undefined;
  let fwdRev1y: number | undefined;
  for (const t of et) {
    if (t.period === "0y") { fwdEps0y = t.growth?.raw; fwdRev0y = t.revenueEstimate?.growth?.raw; }
    if (t.period === "+1y") { fwdEps1y = t.growth?.raw; fwdRev1y = t.revenueEstimate?.growth?.raw; }
  }

  return {
    beat_rate: eh.length ? Math.round(beats / eh.length * 100) : 0,
    quarters_analyzed: eh.length,
    avg_surprise_percent: +avgSurprise.toFixed(2),
    next_earnings_date: nextDate,
    forward_eps_growth_0y: fwdEps0y,
    forward_eps_growth_1y: fwdEps1y,
    forward_revenue_growth_0y: fwdRev0y,
    forward_revenue_growth_1y: fwdRev1y,
  };
}

export async function getOptionsData(ticker: string): Promise<OptionsData> {
  const url = `https://query2.finance.yahoo.com/v7/finance/options/${ticker}`;
  const data = await fetchYahoo(url);
  const chain = data?.optionChain?.result?.[0];
  const calls = chain?.options?.[0]?.calls || [];
  const puts = chain?.options?.[0]?.puts || [];

  const callOI = calls.reduce((s: number, c: any) => s + (c.openInterest || 0), 0);
  const putOI = puts.reduce((s: number, p: any) => s + (p.openInterest || 0), 0);
  const ivs = [...calls, ...puts]
    .map((o: any) => o.impliedVolatility)
    .filter((v: any) => v != null && v > 0);
  const avgIV = ivs.length ? ivs.reduce((s: number, v: number) => s + v, 0) / ivs.length : 0;

  return {
    put_call_ratio: callOI > 0 ? +(putOI / callOI).toFixed(3) : 0,
    avg_implied_volatility: +(avgIV * 100).toFixed(1),
    call_open_interest: callOI,
    put_open_interest: putOI,
  };
}

export async function getMacroData(): Promise<MacroData> {
  const symbols = ["^IRX", "^FVX", "^TNX", "^TYX"];
  const results: number[] = [];

  for (const sym of symbols) {
    const url = `https://query2.finance.yahoo.com/v8/finance/chart/${sym}?interval=1d&range=5d`;
    const data = await fetchYahoo(url);
    const closes = data?.chart?.result?.[0]?.indicators?.quote?.[0]?.close || [];
    const latest = closes.filter((c: any) => c != null).pop() || 0;
    results.push(+(latest as number).toFixed(2));
  }

  return {
    treasury_3m: results[0],
    treasury_5y: results[1],
    treasury_10y: results[2],
    treasury_30y: results[3],
    spread_10y_3m: +(results[2] - results[0]).toFixed(2),
  };
}

export function extractMetrics(summary: any): Metrics {
  const fd = summary?.financialData || {};
  const ks = summary?.defaultKeyStatistics || {};

  // market cap = sharesOutstanding × currentPrice
  const shares = ks.sharesOutstanding?.raw;
  const price = fd.currentPrice?.raw;
  const marketCap = shares && price ? shares * price : ks.enterpriseValue?.raw;

  // PE = price / EPS
  const eps = ks.trailingEps?.raw;
  const pe = eps && price ? price / eps : ks.forwardPE?.raw;

  return {
    market_cap: marketCap,
    pe_ratio: pe,
    pb_ratio: ks.priceToBook?.raw,
    ps_ratio: marketCap && fd.totalRevenue?.raw ? marketCap / fd.totalRevenue.raw : undefined,
    ev_to_ebitda: ks.enterpriseToEbitda?.raw,
    roe: fd.returnOnEquity?.raw,
    gross_margin: fd.grossMargins?.raw,
    net_margin: fd.profitMargins?.raw,
    operating_margin: fd.operatingMargins?.raw,
    debt_to_equity: fd.debtToEquity?.raw ? fd.debtToEquity.raw / 100 : undefined,
    current_ratio: fd.currentRatio?.raw,
    revenue_growth: fd.revenueGrowth?.raw,
    earnings_growth: fd.earningsGrowth?.raw,
    free_cash_flow_yield: fd.freeCashflow?.raw && marketCap
      ? fd.freeCashflow.raw / marketCap
      : undefined,
    earnings_per_share: eps,
    peg_ratio: ks.pegRatio?.raw,
  };
}

export function extractFinancials(summary: any): Financials[] {
  const fd = summary?.financialData || {};
  const ks = summary?.defaultKeyStatistics || {};
  const income = summary?.incomeStatementHistory?.incomeStatementHistory || [];
  const balance = summary?.balanceSheetHistory?.balanceSheetStatements || [];
  const cashflow = summary?.cashflowStatementHistory?.cashflowStatements || [];

  const results: Financials[] = [];

  // TTM 数据从 financialData 模块获取（最完整）
  const today = new Date().toISOString().split("T")[0];
  results.push({
    report_period: today,
    revenue: fd.totalRevenue?.raw,
    net_income: fd.profitMargins?.raw && fd.totalRevenue?.raw
      ? Math.round(fd.profitMargins.raw * fd.totalRevenue.raw)
      : undefined,
    operating_income: fd.operatingMargins?.raw && fd.totalRevenue?.raw
      ? Math.round(fd.operatingMargins.raw * fd.totalRevenue.raw)
      : undefined,
    ebitda: fd.ebitda?.raw,
    gross_profit: fd.grossProfits?.raw,
    interest_expense: undefined,
    ebit: fd.operatingMargins?.raw && fd.totalRevenue?.raw
      ? Math.round(fd.operatingMargins.raw * fd.totalRevenue.raw)
      : undefined,
    total_assets: undefined,
    total_liabilities: undefined,
    shareholders_equity: undefined,
    total_debt: fd.totalDebt?.raw,
    cash_and_equivalents: fd.totalCash?.raw,
    capital_expenditure: fd.operatingCashflow?.raw && fd.freeCashflow?.raw
      ? fd.operatingCashflow.raw - fd.freeCashflow.raw
      : undefined,
    free_cash_flow: fd.freeCashflow?.raw,
    outstanding_shares: ks.sharesOutstanding?.raw,
    research_and_development: undefined,
    depreciation_and_amortization: undefined,
  });

  // 最近4个季度
  const quarterly = summary?.incomeStatementHistoryQuarterly?.incomeStatementHistory || [];
  for (const q of quarterly) {
    results.push({
      report_period: q.endDate?.fmt || "",
      revenue: q.totalRevenue?.raw,
      net_income: q.netIncome?.raw,
      operating_income: q.operatingIncome?.raw,
      ebitda: q.ebitda?.raw,
      gross_profit: q.grossProfit?.raw,
      interest_expense: q.interestExpense?.raw ? Math.abs(q.interestExpense.raw) : undefined,
      ebit: q.ebit?.raw,
      research_and_development: q.researchDevelopment?.raw,
    });
  }

  // 历史年度数据
  const periods = Math.max(income.length, balance.length, cashflow.length);
  for (let i = 0; i < periods; i++) {
    const inc = income[i] || {};
    const bal = balance[i] || {};
    const cf = cashflow[i] || {};

    results.push({
      report_period: inc.endDate?.fmt || bal.endDate?.fmt || cf.endDate?.fmt || "",
      revenue: inc.totalRevenue?.raw,
      net_income: inc.netIncome?.raw,
      operating_income: inc.operatingIncome?.raw,
      ebitda: inc.ebitda?.raw,
      gross_profit: inc.grossProfit?.raw,
      interest_expense: inc.interestExpense?.raw ? Math.abs(inc.interestExpense.raw) : undefined,
      ebit: inc.ebit?.raw,
      total_assets: bal.totalAssets?.raw,
      total_liabilities: bal.totalLiab?.raw,
      shareholders_equity: bal.totalStockholderEquity?.raw,
      total_debt: bal.longTermDebt?.raw,
      cash_and_equivalents: bal.cash?.raw,
      capital_expenditure: cf.capitalExpenditures?.raw ? Math.abs(cf.capitalExpenditures.raw) : undefined,
      free_cash_flow: cf.totalCashFromOperatingActivities?.raw && cf.capitalExpenditures?.raw
        ? cf.totalCashFromOperatingActivities.raw + cf.capitalExpenditures.raw
        : undefined,
      outstanding_shares: bal.commonStock?.raw,
      research_and_development: inc.researchDevelopment?.raw,
      depreciation_and_amortization: cf.depreciation?.raw,
    });
  }

  return results;
}

const POS_WORDS = ["surge", "beat", "growth", "strong", "record", "profit", "upgrade", "buy", "rally", "gain", "soar", "bullish", "outperform"];
const NEG_WORDS = ["miss", "decline", "loss", "cut", "downgrade", "sell", "crash", "drop", "weak", "layoff", "warn", "bearish", "risk", "fall"];

function sentimentFromTitle(title: string): "positive" | "negative" | "neutral" {
  const lower = title.toLowerCase();
  const pos = POS_WORDS.filter((w) => lower.includes(w)).length;
  const neg = NEG_WORDS.filter((w) => lower.includes(w)).length;
  if (pos > neg) return "positive";
  if (neg > pos) return "negative";
  return "neutral";
}

export async function getNews(ticker: string, limit = 30): Promise<NewsItem[]> {
  const resp = await fetch(
    `https://feeds.finance.yahoo.com/rss/2.0/headline?s=${ticker}&region=US&lang=en-US&count=${limit}`,
    { headers: { "User-Agent": "Mozilla/5.0" } },
  );
  if (!resp.ok) return [];
  const text = await resp.text();

  const items = [...text.matchAll(/<item>([\s\S]*?)<\/item>/g)];
  return items.map((match) => {
    const xml = match[1];
    const title = xml.match(/<title>(.*?)<\/title>/)?.[1]?.replace(/&amp;/g, "&").replace(/&lt;/g, "<").replace(/&gt;/g, ">") || "";
    const pubDate = xml.match(/<pubDate>(.*?)<\/pubDate>/)?.[1] || "";
    const source = xml.match(/<source[^>]*>(.*?)<\/source>/)?.[1] || "Yahoo Finance";
    const date = pubDate ? new Date(pubDate).toISOString().split("T")[0] : "";

    return {
      title,
      date,
      source,
      sentiment: sentimentFromTitle(title),
    };
  });
}

export function extractInsiderTrades(summary: any): InsiderTrade[] {
  const transactions = summary?.insiderTransactions?.transactions || [];
  return transactions.slice(0, 50).map((t: any) => ({
    name: t.filerName || "",
    title: t.filerRelation || "",
    date: t.startDate?.fmt || "",
    shares: t.shares?.raw || 0,
    value: t.value?.raw,
  }));
}

export async function fetchAllStockData(ticker: string, startDate: string, endDate: string): Promise<StockData> {
  const { getFinancialsFromAV } = await import("./alphavantage.ts");

  const [summary, prices, news, avData, macro, options] = await Promise.all([
    getQuoteSummary(ticker),
    getPrices(ticker, startDate, endDate),
    getNews(ticker, 20),
    getFinancialsFromAV(ticker),
    getMacroData(),
    getOptionsData(ticker),
  ]);

  // 财报数据：优先 Alpha Vantage（20年），没有则用 Yahoo（4年）
  const yahooFinancials = summary ? extractFinancials(summary) : [];
  let financials: Financials[];

  if (avData.annual.length > 0 || avData.quarterly.length > 0) {
    // Alpha Vantage 有数据：TTM + AV季报 + AV年报
    financials = [
      ...yahooFinancials.slice(0, 1),
      ...avData.quarterly.slice(0, 8),
      ...avData.annual.slice(0, 10),
    ];
  } else {
    // Alpha Vantage 没数据（港股等）：用 Yahoo 全部数据
    financials = yahooFinancials;
  }

  // 合并 metrics + 额外字段
  const baseMetrics = summary ? extractMetrics(summary) : {};
  const extraMetrics = summary ? extractExtraMetrics(summary) : {};

  return {
    ticker,
    prices,
    metrics: { ...baseMetrics, ...extraMetrics },
    financials,
    news,
    insider_trades: summary ? extractInsiderTrades(summary) : [],
    profile: summary ? extractProfile(summary) : { sector: "", industry: "", summary: "" },
    analyst_ratings: summary ? extractAnalystRatings(summary) : { buy: 0, hold: 0, sell: 0 },
    macro,
    short_interest: summary ? extractShortInterest(summary) : { shares_short: 0, short_ratio: 0, short_percent_of_float: 0 },
    options,
    earnings: summary ? extractEarnings(summary) : { beat_rate: 0, quarters_analyzed: 0, avg_surprise_percent: 0 },
  };
}
