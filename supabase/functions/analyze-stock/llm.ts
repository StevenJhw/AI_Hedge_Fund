import { AgentSignal, StockData } from "./types.ts";

const DEEPSEEK_URL = "https://api.deepseek.com/chat/completions";

// 设为 true 使用 mock 数据测试，不调用 LLM API
const TEST_MODE = false;

function mockAgent(ticker: string, agentId: string): AgentSignal {
  const signals: ("bullish" | "bearish" | "neutral")[] = ["bullish", "bearish", "neutral"];
  const hash = (ticker + agentId).split("").reduce((a, c) => a + c.charCodeAt(0), 0);
  return {
    signal: signals[hash % 3],
    confidence: 50 + (hash % 40),
    reasoning: `[TEST] Mock signal for ${ticker} from ${agentId}`,
  };
}

export async function callAgent(
  stockData: StockData,
  systemPrompt: string,
  apiKey: string,
  agentId: string = "unknown",
): Promise<AgentSignal> {
  if (TEST_MODE) {
    return mockAgent(stockData.ticker, agentId);
  }

  const userContent = `Analyze ${stockData.ticker} (${stockData.profile?.sector} / ${stockData.profile?.industry}):

Company: ${stockData.profile?.summary || "N/A"}

Metrics: ${JSON.stringify(stockData.metrics)}

Financials (recent ${stockData.financials.length} periods): ${JSON.stringify(stockData.financials.slice(0, 8))}

Recent prices (last 20 days): ${JSON.stringify(stockData.prices.slice(-20))}

Insider trades (recent): ${JSON.stringify(stockData.insider_trades.slice(0, 15))}

News: ${JSON.stringify(stockData.news)}

Analyst ratings: ${JSON.stringify(stockData.analyst_ratings)}

Short interest: ${JSON.stringify(stockData.short_interest)}

Options sentiment: ${JSON.stringify(stockData.options)}

Earnings: ${JSON.stringify(stockData.earnings)}

Macro (Treasury yields): ${JSON.stringify(stockData.macro)}`;

  const resp = await fetch(DEEPSEEK_URL, {
    method: "POST",
    headers: {
      "Authorization": `Bearer ${apiKey}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      model: "deepseek-v4-pro",
      messages: [
        { role: "system", content: systemPrompt },
        { role: "user", content: userContent },
      ],
      response_format: { type: "json_object" },
      temperature: 0,
      max_tokens: 500,
    }),
  });

  if (!resp.ok) {
    const err = await resp.text();
    throw new Error(`DeepSeek API error: ${resp.status} ${err}`);
  }

  const data = await resp.json();
  const content = data.choices?.[0]?.message?.content || "{}";

  try {
    const parsed = JSON.parse(content);
    return {
      signal: parsed.signal || "neutral",
      confidence: Math.min(100, Math.max(0, parsed.confidence || 50)),
      reasoning: parsed.reasoning || "",
    };
  } catch {
    return { signal: "neutral", confidence: 0, reasoning: "Failed to parse LLM response" };
  }
}

export async function generateSummary(
  ticker: string,
  stockData: StockData,
  agentResults: Record<string, AgentSignal>,
  consensus: { signal: string; score: number },
  apiKey: string,
): Promise<string> {
  if (TEST_MODE) {
    return `[TEST] ${ticker} 综合分析：共识 ${consensus.signal}，得分 ${consensus.score}`;
  }

  const agentSummaries = Object.entries(agentResults)
    .map(([id, sig]) => `${id}: ${sig.signal}(${sig.confidence}%) - ${sig.reasoning}`)
    .join("\n");

  const prompt = `你是一个投资分析助手。请用中文，用大白话（普通人能看懂的语言）总结以下对 ${ticker} 的分析结果。

股票: ${ticker} (${stockData.profile?.sector} / ${stockData.profile?.industry})
当前价格: $${stockData.prices[stockData.prices.length - 1]?.close || "N/A"}
PE: ${stockData.metrics.pe_ratio || "N/A"} | 收入增长: ${stockData.metrics.revenue_growth ? (stockData.metrics.revenue_growth * 100).toFixed(1) + "%" : "N/A"}

5位投资大师的判断:
${agentSummaries}

综合共识: ${consensus.signal} (得分: ${consensus.score})

要求:
1. 用 3-5 句话总结，像朋友聊天一样说人话
2. 说清楚：这只股票现在值不值得买，为什么
3. 主要的风险是什么
4. 不要用专业术语，不要说"PE ratio"，要说"股价相对于赚钱能力贵不贵"
5. 直接给结论，不要废话`;

  const resp = await fetch(DEEPSEEK_URL, {
    method: "POST",
    headers: {
      "Authorization": `Bearer ${apiKey}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      model: "deepseek-v4-pro",
      messages: [
        { role: "user", content: prompt },
      ],
      temperature: 0.1,
      max_tokens: 300,
    }),
  });

  if (!resp.ok) {
    return `${ticker} 综合评分: ${consensus.signal}`;
  }

  const data = await resp.json();
  return data.choices?.[0]?.message?.content?.trim() || `${ticker} 综合评分: ${consensus.signal}`;
}
