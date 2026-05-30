import { Financials } from "./types.ts";

const AV_BASE = "https://www.alphavantage.co/query";

// 多 key 轮换：用逗号分隔存在环境变量里
// ALPHA_VANTAGE_API_KEYS=key1,key2,key3,key4
function getApiKeys(): string[] {
  const multi = Deno.env.get("ALPHA_VANTAGE_API_KEYS");
  if (multi) return multi.split(",").map((k) => k.trim());
  const single = Deno.env.get("ALPHA_VANTAGE_API_KEY");
  if (single) return [single];
  return ["M97ECM0IJ7A2249R"];
}

let _keyIndex = 0;

async function fetchAV(params: Record<string, string>): Promise<any> {
  const keys = getApiKeys();

  // 尝试所有 key，遇到 rate limit 就换下一个
  for (let attempt = 0; attempt < keys.length; attempt++) {
    const key = keys[_keyIndex % keys.length];
    const query = new URLSearchParams({ ...params, apikey: key }).toString();
    const resp = await fetch(`${AV_BASE}?${query}`);
    if (!resp.ok) return null;

    const data = await resp.json();
    if (data?.Note || data?.Information) {
      // rate limit hit, 换下一个 key
      _keyIndex++;
      continue;
    }
    return data;
  }

  return null; // 所有 key 都用完了
}

function num(val: string | undefined): number | undefined {
  if (!val || val === "None" || val === "0") return undefined;
  const n = Number(val);
  return isNaN(n) ? undefined : n;
}

function mapIncomeStatement(r: any): Partial<Financials> {
  return {
    report_period: r.fiscalDateEnding,
    revenue: num(r.totalRevenue),
    net_income: num(r.netIncome),
    operating_income: num(r.operatingIncome),
    gross_profit: num(r.grossProfit),
    ebit: num(r.ebit),
    ebitda: num(r.ebitda),
    interest_expense: num(r.interestExpense),
    research_and_development: num(r.researchAndDevelopment),
  };
}

function mapBalanceSheet(r: any): Partial<Financials> {
  return {
    report_period: r.fiscalDateEnding,
    total_assets: num(r.totalAssets),
    total_liabilities: num(r.totalLiabilities),
    shareholders_equity: num(r.totalShareholderEquity),
    total_debt: num(r.longTermDebt) || num(r.shortLongTermDebtTotal),
    cash_and_equivalents: num(r.cashAndCashEquivalentsAtCarryingValue) || num(r.cashAndShortTermInvestments),
    outstanding_shares: num(r.commonStockSharesOutstanding),
  };
}

function mapCashFlow(r: any): Partial<Financials> {
  const opCF = num(r.operatingCashflow);
  const capex = num(r.capitalExpenditures);
  return {
    report_period: r.fiscalDateEnding,
    capital_expenditure: capex,
    free_cash_flow: opCF && capex ? opCF - capex : undefined,
    depreciation_and_amortization: num(r.depreciationDepletionAndAmortization),
  };
}

function mergeByPeriod(
  income: Partial<Financials>[],
  balance: Partial<Financials>[],
  cashflow: Partial<Financials>[],
): Financials[] {
  const map = new Map<string, Financials>();

  for (const item of income) {
    const period = item.report_period || "";
    map.set(period, { ...map.get(period), ...item } as Financials);
  }
  for (const item of balance) {
    const period = item.report_period || "";
    map.set(period, { ...map.get(period), ...item } as Financials);
  }
  for (const item of cashflow) {
    const period = item.report_period || "";
    map.set(period, { ...map.get(period), ...item } as Financials);
  }

  return [...map.values()].sort((a, b) =>
    (b.report_period || "").localeCompare(a.report_period || "")
  );
}

export async function getFinancialsFromAV(
  ticker: string,
  type: "annual" | "quarterly" | "both" = "both",
): Promise<{ annual: Financials[]; quarterly: Financials[] }> {
  const [incData, bsData, cfData] = await Promise.all([
    fetchAV({ function: "INCOME_STATEMENT", symbol: ticker }),
    fetchAV({ function: "BALANCE_SHEET", symbol: ticker }),
    fetchAV({ function: "CASH_FLOW", symbol: ticker }),
  ]);

  let annual: Financials[] = [];
  let quarterly: Financials[] = [];

  if (type === "annual" || type === "both") {
    const incAnnual = (incData?.annualReports || []).map(mapIncomeStatement);
    const bsAnnual = (bsData?.annualReports || []).map(mapBalanceSheet);
    const cfAnnual = (cfData?.annualReports || []).map(mapCashFlow);
    annual = mergeByPeriod(incAnnual, bsAnnual, cfAnnual);
  }

  if (type === "quarterly" || type === "both") {
    const incQ = (incData?.quarterlyReports || []).map(mapIncomeStatement);
    const bsQ = (bsData?.quarterlyReports || []).map(mapBalanceSheet);
    const cfQ = (cfData?.quarterlyReports || []).map(mapCashFlow);
    quarterly = mergeByPeriod(incQ, bsQ, cfQ);
  }

  return { annual, quarterly };
}
