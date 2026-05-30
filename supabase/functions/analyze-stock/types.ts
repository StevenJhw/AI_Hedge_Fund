export interface Price {
  date: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export interface Metrics {
  market_cap?: number;
  pe_ratio?: number;
  pb_ratio?: number;
  ps_ratio?: number;
  ev_to_ebitda?: number;
  roe?: number;
  gross_margin?: number;
  net_margin?: number;
  operating_margin?: number;
  debt_to_equity?: number;
  current_ratio?: number;
  revenue_growth?: number;
  earnings_growth?: number;
  free_cash_flow_yield?: number;
  earnings_per_share?: number;
  peg_ratio?: number;
}

export interface Financials {
  report_period: string;
  revenue?: number;
  net_income?: number;
  operating_income?: number;
  ebitda?: number;
  free_cash_flow?: number;
  total_assets?: number;
  total_liabilities?: number;
  shareholders_equity?: number;
  total_debt?: number;
  cash_and_equivalents?: number;
  capital_expenditure?: number;
  research_and_development?: number;
  outstanding_shares?: number;
  gross_profit?: number;
  interest_expense?: number;
  ebit?: number;
  depreciation_and_amortization?: number;
}

export interface NewsItem {
  title: string;
  date: string;
  source: string;
  sentiment: "positive" | "negative" | "neutral";
}

export interface InsiderTrade {
  name: string;
  title: string;
  date: string;
  shares: number;
  value?: number;
}

export interface CompanyProfile {
  sector: string;
  industry: string;
  employees?: number;
  summary: string;
}

export interface AnalystRatings {
  buy: number;
  hold: number;
  sell: number;
  target_price_mean?: number;
  target_price_high?: number;
  target_price_low?: number;
}

export interface MacroData {
  treasury_3m: number;
  treasury_5y: number;
  treasury_10y: number;
  treasury_30y: number;
  spread_10y_3m: number;
}

export interface ShortInterest {
  shares_short: number;
  short_ratio: number;
  short_percent_of_float: number;
}

export interface OptionsData {
  put_call_ratio: number;
  avg_implied_volatility: number;
  call_open_interest: number;
  put_open_interest: number;
}

export interface EarningsData {
  beat_rate: number;
  quarters_analyzed: number;
  avg_surprise_percent: number;
  next_earnings_date?: string;
  forward_eps_growth_0y?: number;
  forward_eps_growth_1y?: number;
  forward_revenue_growth_0y?: number;
  forward_revenue_growth_1y?: number;
}

export interface StockData {
  ticker: string;
  prices: Price[];
  metrics: Metrics & {
    beta?: number;
    week52_change?: number;
    dividend_yield?: number;
    insiders_percent_held?: number;
    institutions_percent_held?: number;
  };
  financials: Financials[];
  news: NewsItem[];
  insider_trades: InsiderTrade[];
  profile: CompanyProfile;
  analyst_ratings: AnalystRatings;
  macro: MacroData;
  short_interest: ShortInterest;
  options: OptionsData;
  earnings: EarningsData;
}

export interface AgentSignal {
  signal: "bullish" | "bearish" | "neutral";
  confidence: number;
  reasoning: string;
}

export interface AnalysisResult {
  ticker: string;
  date: string;
  agents: Record<string, AgentSignal>;
  consensus: {
    signal: "bullish" | "bearish" | "neutral";
    score: number;
  };
  data_summary?: {
    prices_days: number;
    financials_periods: number;
    news_count: number;
    insider_trades_count: number;
  };
  previous_signals?: Record<string, any>[];
}
