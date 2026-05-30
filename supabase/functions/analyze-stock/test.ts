// 本地测试脚本：模拟 Edge Function 被调用
// 运行：deno run --allow-net --allow-env test.ts

import { fetchAllStockData } from "./yahoo.ts";
import { callAgent } from "./llm.ts";
import { AGENTS } from "./agents.ts";
import { AgentSignal } from "./types.ts";

const ticker = Deno.args[0] || "AAPL";
console.log(`\n🔍 Testing analyze-stock for: ${ticker}\n`);

// 1. 拉数据
console.log("📊 Fetching data from Yahoo Finance...");
const endDate = new Date().toISOString().split("T")[0];
const startDate = new Date(Date.now() - 365 * 86400_000).toISOString().split("T")[0];

const stockData = await fetchAllStockData(ticker, startDate, endDate);
console.log(`  Prices: ${stockData.prices.length} days`);
console.log(`  Metrics: ${Object.keys(stockData.metrics).filter(k => (stockData.metrics as any)[k] != null).length} fields`);
console.log(`  Financials: ${stockData.financials.length} periods`);
console.log(`  Insider trades: ${stockData.insider_trades.length}`);

if (stockData.prices.length === 0 && Object.keys(stockData.metrics).length === 0) {
  console.log("\n❌ No data found. Check ticker symbol.");
  Deno.exit(1);
}

// 2. 跑 5 个 Agent
const apiKey = Deno.env.get("DEEPSEEK_API_KEY") || "test-key";
console.log(`\n🤖 Running agents (${apiKey === "test-key" ? "MOCK" : "REAL DeepSeek"})...\n`);
const results: Record<string, AgentSignal> = {};

for (const [id, agent] of Object.entries(AGENTS)) {
  const signal = await callAgent(stockData, agent.prompt, apiKey, id);
  results[id] = signal;
  const emoji = signal.signal === "bullish" ? "🟢" : signal.signal === "bearish" ? "🔴" : "⚪";
  console.log(`  ${emoji} ${agent.name}: ${signal.signal} (${signal.confidence}%) - ${signal.reasoning}`);
}

// 3. 计算共识
let score = 0;
let totalWeight = 0;
for (const sig of Object.values(results)) {
  const w = sig.confidence / 100;
  if (sig.signal === "bullish") score += w;
  else if (sig.signal === "bearish") score -= w;
  totalWeight += w;
}
const normalized = totalWeight > 0 ? score / totalWeight : 0;
const consensus = normalized > 0.2 ? "bullish" : normalized < -0.2 ? "bearish" : "neutral";

console.log(`\n📈 Consensus: ${consensus} (score: ${normalized.toFixed(2)})`);
console.log("\n✅ Test complete!\n");
