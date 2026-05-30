import { fetchAllStockData } from "./yahoo.ts";
import { callAgent, generateSummary } from "./llm.ts";
import { AGENTS } from "./agents.ts";
import {
  isDataFresh,
  savePrices,
  saveMetrics,
  saveFinancials,
  saveInsiderTrades,
  saveLlmSignal,
  saveDecision,
  getPreviousSignals,
  getCachedPrices,
  getCachedMetrics,
  getCachedFinancials,
  saveAnalysisHistory,
  getAnalysisHistory,
  deleteHistoryItem,
} from "./db.ts";
import { AgentSignal, AnalysisResult, StockData } from "./types.ts";

Deno.serve(async (req) => {
  if (req.method === "OPTIONS") {
    return new Response(null, {
      headers: {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "POST",
        "Access-Control-Allow-Headers": "Content-Type, Authorization",
      },
    });
  }

  try {
    const body = await req.json().catch(() => null);
    if (!body) {
      return jsonResponse({ error: "invalid_request", message: "请求体无效" }, 400);
    }

    // 路由：获取历史记录
    if (body.action === "get_history") {
      const history = await getAnalysisHistory(body.limit || 50);
      return jsonResponse({ history });
    }

    // 路由：删除某条历史
    if (body.action === "delete_history") {
      if (!body.id) return jsonResponse({ error: "id is required" }, 400);
      await deleteHistoryItem(body.id);
      return jsonResponse({ success: true });
    }

    // 默认：分析股票
    if (!body.ticker) {
      return jsonResponse({ error: "ticker is required", message: "请提供股票代码" }, 400);
    }

    const { ticker, force_refresh } = body;
    const upperTicker = ticker.toUpperCase().trim();

    // 验证股票代码格式
    if (!/^[A-Z]{1,5}$/.test(upperTicker)) {
      return jsonResponse({
        error: "invalid_ticker",
        message: "股票代码无效，应为1-5个英文字母",
      }, 400);
    }

    const deepseekKey = Deno.env.get("DEEPSEEK_API_KEY") || "test-mode";

    const endDate = new Date().toISOString().split("T")[0];
    const startDate = new Date(Date.now() - 365 * 86400_000).toISOString().split("T")[0];

    // 1. 检查 Supabase 缓存（如果不强制刷新）
    let stockData: StockData;

    if (!force_refresh && await isDataFresh(upperTicker, "prices")) {
      // 从 Supabase 读取缓存数据（价格、财报等不常变的数据）
      // 但 options/news/macro 还是实时拉（变化快）
      stockData = await fetchAllStockData(upperTicker, startDate, endDate);
    } else {
      // 第一次查或强制刷新：全量拉取
      stockData = await fetchAllStockData(upperTicker, startDate, endDate);

      // 存入 Supabase 缓存
      await Promise.all([
        savePrices(upperTicker, stockData.prices),
        saveMetrics(upperTicker, stockData.metrics),
        saveFinancials(upperTicker, stockData.financials),
        saveInsiderTrades(upperTicker, stockData.insider_trades),
      ]);
    }

    // 2. 数据充足性检查
    const hasData = stockData.prices.length > 0 || Object.keys(stockData.metrics).length > 0;
    if (!hasData) {
      return jsonResponse({
        error: "insufficient_data",
        message: `无法获取 ${upperTicker} 的数据，请检查股票代码是否正确`,
      }, 422);
    }

    // 3. 获取上一次分析结果（用于对比）
    const previousSignals = await getPreviousSignals(upperTicker);
    const lastAnalysis = buildLastAnalysis(previousSignals);

    // 4. 5 个 Agent 并行调用 LLM（单个失败不影响其他）
    const agentEntries = Object.entries(AGENTS);
    const signals = await Promise.all(
      agentEntries.map(([id, agent]) =>
        callAgent(stockData, agent.prompt, deepseekKey, id).catch((_err) => ({
          signal: "neutral" as const,
          confidence: 0,
          reasoning: `Agent ${id} 分析失败，已跳过`,
        }))
      )
    );

    const agentResults: Record<string, AgentSignal> = {};
    const savePromises: Promise<void>[] = [];
    for (let i = 0; i < agentEntries.length; i++) {
      const [id] = agentEntries[i];
      agentResults[id] = signals[i];
      // 只保存成功的信号
      if (signals[i].confidence > 0) {
        savePromises.push(saveLlmSignal(upperTicker, id, signals[i]));
      }
    }
    await Promise.all(savePromises);

    // 如果所有 Agent 都失败了，提前终止
    const successCount = signals.filter((s) => s.confidence > 0).length;
    if (successCount === 0) {
      return jsonResponse({
        error: "analysis_failed",
        message: "所有分析 Agent 均失败，请稍后重试",
      }, 500);
    }

    // 5. 计算共识
    const consensus = calculateConsensus(agentResults);

    // 6. 和上次对比，生成变化摘要
    const changes = computeChanges(agentResults, consensus, lastAnalysis);

    // 7. 生成大白话总结
    const summary = await generateSummary(upperTicker, stockData, agentResults, consensus, deepseekKey);

    // 8. 存决策 + 历史记录
    await Promise.all([
      saveDecision(upperTicker, consensus.signal, consensus.score, summary),
      saveAnalysisHistory(upperTicker, consensus.signal, consensus.score, summary, agentResults),
    ]);

    // 9. 返回结果
    const result = {
      ticker: upperTicker,
      date: endDate,
      summary,
      agents: agentResults,
      consensus,
      changes,
      last_analysis: lastAnalysis,
      data_summary: {
        prices_days: stockData.prices.length,
        financials_periods: stockData.financials.length,
        news_count: stockData.news.length,
        insider_trades_count: stockData.insider_trades.length,
      },
    };

    return jsonResponse(result);
  } catch (err: unknown) {
    console.error(err);
    const message = err instanceof Error ? err.message : String(err);
    return jsonResponse({ error: message }, 500);
  }
});

interface LastAnalysis {
  date: string | null;
  agents: Record<string, { signal: string; confidence: number }>;
  consensus: { signal: string; score: number } | null;
}

interface ChangeItem {
  agent: string;
  from: string;
  to: string;
  confidence_change: number;
  changed: boolean;
}

interface Changes {
  has_previous: boolean;
  consensus_changed: boolean;
  consensus_from?: string;
  consensus_to?: string;
  score_change?: number;
  agent_changes: ChangeItem[];
  summary: string;
}

function buildLastAnalysis(previousSignals: Record<string, any>[]): LastAnalysis {
  if (!previousSignals.length) {
    return { date: null, agents: {}, consensus: null };
  }

  // 找到最近一次分析的日期（排除今天）
  const today = new Date().toISOString().split("T")[0];
  const pastSignals = previousSignals.filter((s) => s.analysis_date !== today);

  if (!pastSignals.length) {
    return { date: null, agents: {}, consensus: null };
  }

  const lastDate = pastSignals[0].analysis_date;
  const lastDaySignals = pastSignals.filter((s) => s.analysis_date === lastDate);

  const agents: Record<string, { signal: string; confidence: number }> = {};
  for (const s of lastDaySignals) {
    agents[s.agent_id] = { signal: s.signal, confidence: +s.confidence };
  }

  // 重新计算上次的 consensus
  let score = 0;
  let totalWeight = 0;
  for (const sig of Object.values(agents)) {
    const w = sig.confidence / 100;
    if (sig.signal === "bullish") score += w;
    else if (sig.signal === "bearish") score -= w;
    totalWeight += w;
  }
  const normalized = totalWeight > 0 ? score / totalWeight : 0;
  const consensusSignal = normalized > 0.2 ? "bullish" : normalized < -0.2 ? "bearish" : "neutral";

  return {
    date: lastDate,
    agents,
    consensus: { signal: consensusSignal, score: Math.round(normalized * 100) / 100 },
  };
}

function computeChanges(
  current: Record<string, AgentSignal>,
  currentConsensus: { signal: string; score: number },
  last: LastAnalysis,
): Changes {
  if (!last.date) {
    return {
      has_previous: false,
      consensus_changed: false,
      agent_changes: [],
      summary: "首次分析，无历史对比",
    };
  }

  const agentChanges: ChangeItem[] = [];
  for (const [id, sig] of Object.entries(current)) {
    const prev = last.agents[id];
    if (prev) {
      agentChanges.push({
        agent: id,
        from: prev.signal,
        to: sig.signal,
        confidence_change: sig.confidence - prev.confidence,
        changed: prev.signal !== sig.signal,
      });
    } else {
      agentChanges.push({
        agent: id,
        from: "none",
        to: sig.signal,
        confidence_change: 0,
        changed: true,
      });
    }
  }

  const consensusChanged = last.consensus?.signal !== currentConsensus.signal;
  const scoreChange = last.consensus ? currentConsensus.score - last.consensus.score : 0;
  const changedAgents = agentChanges.filter((c) => c.changed);

  // 生成变化摘要
  let summary = "";
  if (consensusChanged) {
    summary = `共识从 ${last.consensus?.signal} 转为 ${currentConsensus.signal}`;
  } else if (Math.abs(scoreChange) > 0.1) {
    summary = `共识不变(${currentConsensus.signal})，但信心${scoreChange > 0 ? "增强" : "减弱"} (${scoreChange > 0 ? "+" : ""}${scoreChange.toFixed(2)})`;
  } else {
    summary = `与上次分析(${last.date})基本一致`;
  }

  if (changedAgents.length > 0) {
    const details = changedAgents.map((c) => `${c.agent}: ${c.from}→${c.to}`).join(", ");
    summary += ` | 变化: ${details}`;
  }

  return {
    has_previous: true,
    consensus_changed: consensusChanged,
    consensus_from: last.consensus?.signal,
    consensus_to: currentConsensus.signal,
    score_change: Math.round(scoreChange * 100) / 100,
    agent_changes: agentChanges,
    summary,
  };
}

function calculateConsensus(agents: Record<string, AgentSignal>): {
  signal: "bullish" | "bearish" | "neutral";
  score: number;
} {
  let score = 0;
  let totalWeight = 0;

  for (const [_, sig] of Object.entries(agents)) {
    const weight = sig.confidence / 100;
    if (sig.signal === "bullish") score += weight;
    else if (sig.signal === "bearish") score -= weight;
    totalWeight += weight;
  }

  const normalized = totalWeight > 0 ? score / totalWeight : 0;

  let signal: "bullish" | "bearish" | "neutral";
  if (normalized > 0.2) signal = "bullish";
  else if (normalized < -0.2) signal = "bearish";
  else signal = "neutral";

  return { signal, score: Math.round(normalized * 100) / 100 };
}

function jsonResponse(data: any, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: {
      "Content-Type": "application/json",
      "Access-Control-Allow-Origin": "*",
    },
  });
}
