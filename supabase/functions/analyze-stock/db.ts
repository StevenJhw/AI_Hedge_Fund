import { createClient } from "https://esm.sh/@supabase/supabase-js@2";
import { StockData, AgentSignal, AnalysisResult } from "./types.ts";

export function getSupabaseClient() {
  return createClient(
    Deno.env.get("SUPABASE_URL")!,
    Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!,
  );
}

export async function isDataFresh(ticker: string, dataType: string): Promise<boolean> {
  const sb = getSupabaseClient();
  const { data } = await sb
    .from("data_freshness")
    .select("next_fetch_after")
    .eq("ticker", ticker)
    .eq("data_type", dataType)
    .maybeSingle();

  if (!data) return false;
  return new Date() < new Date(data.next_fetch_after);
}

export async function markFresh(ticker: string, dataType: string, hoursValid: number) {
  const sb = getSupabaseClient();
  const now = new Date();
  const next = new Date(now.getTime() + hoursValid * 3600_000);

  await sb.from("data_freshness").upsert({
    ticker,
    data_type: dataType,
    last_fetched_at: now.toISOString(),
    next_fetch_after: next.toISOString(),
    fetch_status: "ok",
  });
}

export async function savePrices(ticker: string, prices: StockData["prices"]) {
  const sb = getSupabaseClient();
  const rows = prices.map((p) => ({
    ticker,
    trade_date: p.date,
    open: p.open,
    high: p.high,
    low: p.low,
    close: p.close,
    volume: p.volume,
  }));
  await sb.from("prices").upsert(rows);
  await markFresh(ticker, "prices", 16);
}

export async function saveMetrics(ticker: string, metrics: StockData["metrics"]) {
  const sb = getSupabaseClient();
  const today = new Date().toISOString().split("T")[0];
  await sb.from("metrics_daily").upsert({
    ticker,
    snapshot_date: today,
    market_cap: metrics.market_cap,
    pe_ratio: metrics.pe_ratio,
    pb_ratio: metrics.pb_ratio,
    ps_ratio: metrics.ps_ratio,
    ev_to_ebitda: metrics.ev_to_ebitda,
    roe: metrics.roe,
    gross_margin: metrics.gross_margin,
    net_margin: metrics.net_margin,
    operating_margin: metrics.operating_margin,
    debt_to_equity: metrics.debt_to_equity,
    current_ratio: metrics.current_ratio,
    revenue_growth: metrics.revenue_growth,
    earnings_growth: metrics.earnings_growth,
    free_cash_flow_yield: metrics.free_cash_flow_yield,
    earnings_per_share: metrics.earnings_per_share,
    peg_ratio: metrics.peg_ratio,
  });
  await markFresh(ticker, "metrics", 16);
}

export async function saveFinancials(ticker: string, financials: StockData["financials"]) {
  const sb = getSupabaseClient();
  const rows = financials.map((f) => ({
    ticker,
    report_period: f.report_period,
    period_type: "annual",
    revenue: f.revenue,
    net_income: f.net_income,
    operating_income: f.operating_income,
    ebitda: f.ebitda,
    free_cash_flow: f.free_cash_flow,
    total_assets: f.total_assets,
    total_liabilities: f.total_liabilities,
    shareholders_equity: f.shareholders_equity,
    total_debt: f.total_debt,
    cash_and_equivalents: f.cash_and_equivalents,
    shares_outstanding: f.outstanding_shares,
    capital_expenditure: f.capital_expenditure,
    depreciation_and_amortization: f.depreciation_and_amortization,
    research_and_development: f.research_and_development,
    gross_profit: f.gross_profit,
    interest_expense: f.interest_expense,
    ebit: f.ebit,
  }));
  await sb.from("financials").upsert(rows);
  await markFresh(ticker, "financials", 2160); // 90 days
}

export async function saveInsiderTrades(ticker: string, trades: StockData["insider_trades"]) {
  const sb = getSupabaseClient();
  const rows = trades.map((t) => ({
    ticker,
    insider_name: t.name,
    title: t.title,
    transaction_date: t.date,
    transaction_type: t.shares < 0 ? "sell" : "buy",
    shares: t.shares,
    total_value: t.value,
  }));
  await sb.from("insider_trades").upsert(rows, { onConflict: "ticker,insider_name,transaction_date,shares" });
  await markFresh(ticker, "insider_trades", 72); // 3 days
}

export async function saveLlmSignal(
  ticker: string,
  agentId: string,
  signal: AgentSignal,
) {
  const sb = getSupabaseClient();
  const today = new Date().toISOString().split("T")[0];
  await sb.from("llm_signals").insert({
    ticker,
    analysis_date: today,
    agent_id: agentId,
    signal: signal.signal,
    confidence: signal.confidence,
    reasoning: signal.reasoning,
    model_used: "deepseek-v4-pro",
  });
}

export async function saveDecision(
  ticker: string,
  action: string,
  score: number,
  reasoning: string,
) {
  const sb = getSupabaseClient();
  const today = new Date().toISOString().split("T")[0];
  await sb.from("decisions").insert({
    analysis_date: today,
    ticker,
    action,
    consensus_score: score,
    reasoning,
  });
}

export async function getPreviousSignals(ticker: string): Promise<Record<string, any>[]> {
  const sb = getSupabaseClient();
  // 拿最近 50 条，然后在应用层去重（取每个 agent 每天最新一条）
  const { data } = await sb
    .from("llm_signals")
    .select("agent_id, signal, confidence, analysis_date")
    .eq("ticker", ticker)
    .order("created_at", { ascending: false })
    .limit(50);

  if (!data) return [];

  // 按 analysis_date + agent_id 去重，只保留每组最新一条
  const seen = new Set<string>();
  const deduped: Record<string, any>[] = [];
  for (const row of data) {
    const key = `${row.analysis_date}_${row.agent_id}`;
    if (!seen.has(key)) {
      seen.add(key);
      deduped.push(row);
    }
  }
  return deduped;
}

// ── 历史记录 ─────────────────────────────────────────────────────────

export async function saveAnalysisHistory(
  ticker: string,
  signal: string,
  score: number,
  summary: string,
  agents: Record<string, any>,
) {
  const sb = getSupabaseClient();
  const today = new Date().toISOString().split("T")[0];
  await sb.from("analysis_history").insert({
    ticker,
    analysis_date: today,
    consensus_signal: signal,
    consensus_score: score,
    summary,
    agents,
  });
}

export async function getAnalysisHistory(limit = 50): Promise<Record<string, any>[]> {
  const sb = getSupabaseClient();
  const { data } = await sb
    .from("analysis_history")
    .select("*")
    .order("created_at", { ascending: false })
    .limit(limit);
  return data || [];
}

export async function deleteHistoryItem(id: number): Promise<void> {
  const sb = getSupabaseClient();
  await sb.from("analysis_history").delete().eq("id", id);
}

// ── 缓存读取 ─────────────────────────────────────────────────────────

export async function getCachedPrices(ticker: string, startDate: string, endDate: string): Promise<StockData["prices"] | null> {
  if (!await isDataFresh(ticker, "prices")) return null;
  const sb = getSupabaseClient();
  const { data } = await sb
    .from("prices")
    .select("*")
    .eq("ticker", ticker)
    .gte("trade_date", startDate)
    .lte("trade_date", endDate)
    .order("trade_date");
  if (!data || data.length === 0) return null;
  return data.map((r: any) => ({
    date: r.trade_date,
    open: +r.open,
    high: +r.high,
    low: +r.low,
    close: +r.close,
    volume: +r.volume,
  }));
}

export async function getCachedMetrics(ticker: string): Promise<StockData["metrics"] | null> {
  if (!await isDataFresh(ticker, "metrics")) return null;
  const sb = getSupabaseClient();
  const { data } = await sb
    .from("metrics_daily")
    .select("*")
    .eq("ticker", ticker)
    .order("snapshot_date", { ascending: false })
    .limit(1)
    .maybeSingle();
  if (!data) return null;
  return {
    market_cap: data.market_cap,
    pe_ratio: data.pe_ratio ? +data.pe_ratio : undefined,
    pb_ratio: data.pb_ratio ? +data.pb_ratio : undefined,
    ps_ratio: data.ps_ratio ? +data.ps_ratio : undefined,
    ev_to_ebitda: data.ev_to_ebitda ? +data.ev_to_ebitda : undefined,
    roe: data.roe ? +data.roe : undefined,
    gross_margin: data.gross_margin ? +data.gross_margin : undefined,
    net_margin: data.net_margin ? +data.net_margin : undefined,
    operating_margin: data.operating_margin ? +data.operating_margin : undefined,
    debt_to_equity: data.debt_to_equity ? +data.debt_to_equity : undefined,
    current_ratio: data.current_ratio ? +data.current_ratio : undefined,
    revenue_growth: data.revenue_growth ? +data.revenue_growth : undefined,
    earnings_growth: data.earnings_growth ? +data.earnings_growth : undefined,
    free_cash_flow_yield: data.free_cash_flow_yield ? +data.free_cash_flow_yield : undefined,
    earnings_per_share: data.earnings_per_share ? +data.earnings_per_share : undefined,
    peg_ratio: data.peg_ratio ? +data.peg_ratio : undefined,
  };
}

export async function getCachedFinancials(ticker: string): Promise<StockData["financials"] | null> {
  if (!await isDataFresh(ticker, "financials")) return null;
  const sb = getSupabaseClient();
  const { data } = await sb
    .from("financials")
    .select("*")
    .eq("ticker", ticker)
    .order("report_period", { ascending: false })
    .limit(20);
  if (!data || data.length === 0) return null;
  return data.map((r: any) => ({
    report_period: r.report_period,
    revenue: r.revenue,
    net_income: r.net_income,
    operating_income: r.operating_income,
    ebitda: r.ebitda,
    free_cash_flow: r.free_cash_flow,
    total_assets: r.total_assets,
    total_liabilities: r.total_liabilities,
    shareholders_equity: r.shareholders_equity,
    total_debt: r.total_debt,
    cash_and_equivalents: r.cash_and_equivalents,
    capital_expenditure: r.capital_expenditure,
    outstanding_shares: r.shares_outstanding,
    research_and_development: r.research_and_development,
    gross_profit: r.gross_profit,
    interest_expense: r.interest_expense,
    ebit: r.ebit,
    depreciation_and_amortization: r.depreciation_and_amortization,
  }));
}
