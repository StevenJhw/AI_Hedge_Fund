import 'dart:async';
import 'package:flutter/material.dart';
import '../models/analysis_result.dart';
import '../services/api_service.dart';
import '../services/ticker_search.dart';
import '../widgets/signal_badge.dart';

class AnalysisScreen extends StatefulWidget {
  const AnalysisScreen({super.key});

  @override
  State<AnalysisScreen> createState() => _AnalysisScreenState();
}

class _AnalysisScreenState extends State<AnalysisScreen> {
  final _controller = TextEditingController();
  final _api = ApiService();
  final _searchService = TickerSearchService();
  AnalysisResult? _result;
  bool _loading = false;
  String? _error;
  List<TickerMatch> _suggestions = [];
  Timer? _debounce;

  Future<void> _analyze() async {
    final ticker = _controller.text.trim().toUpperCase();
    if (ticker.isEmpty) return;

    // 如果输入包含中文但没有通过搜索选择，提示用户
    if (RegExp(r'[一-龥]').hasMatch(ticker)) {
      setState(() => _error = '请从搜索建议中选择股票');
      return;
    }

    // 输入验证：只允许 1-5 个字母
    if (!RegExp(r'^[A-Z]{1,5}$').hasMatch(ticker)) {
      setState(() => _error = '请输入有效的股票代码，或用中文搜索后选择');
      return;
    }

    setState(() => _suggestions = []);

    setState(() {
      _loading = true;
      _error = null;
      _result = null;
    });

    try {
      final result = await _api.analyzeStock(ticker);

      // 验证返回数据完整性
      if (result.ticker.isEmpty || result.agents.isEmpty) {
        setState(() => _error = '返回数据不完整，请重试');
        return;
      }

      setState(() => _result = result);
    } on FormatException {
      setState(() => _error = '服务器返回数据格式错误，请稍后重试');
    } catch (e) {
      final msg = e.toString().replaceFirst('Exception: ', '');
      if (msg.contains('SocketException') || msg.contains('ClientException')) {
        setState(() => _error = '网络连接失败，请检查网络后重试');
      } else if (msg.contains('TimeoutException')) {
        setState(() => _error = '请求超时，服务器可能正忙，请稍后重试');
      } else {
        setState(() => _error = msg);
      }
    } finally {
      setState(() => _loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: const Color(0xFF0F1419),
      appBar: AppBar(
        title: const Text('AI 投资分析', style: TextStyle(fontWeight: FontWeight.bold)),
        backgroundColor: const Color(0xFF0F1419),
        elevation: 0,
      ),
      body: Column(
        children: [
          _buildSearchBar(),
          Expanded(
            child: _loading
                ? _buildLoading()
                : _error != null
                    ? _buildError()
                    : _result != null
                        ? _buildResult()
                        : _buildEmpty(),
          ),
        ],
      ),
    );
  }

  void _onSearchChanged(String query) {
    _debounce?.cancel();
    if (query.trim().isEmpty) {
      setState(() => _suggestions = []);
      return;
    }
    _debounce = Timer(const Duration(milliseconds: 400), () async {
      final results = await _searchService.search(query);
      if (mounted) setState(() => _suggestions = results);
    });
  }

  void _selectTicker(TickerMatch match) {
    _controller.text = match.symbol;
    setState(() => _suggestions = []);
    _analyze();
  }

  Widget _buildSearchBar() {
    return Padding(
      padding: const EdgeInsets.fromLTRB(16, 8, 16, 0),
      child: Column(
        children: [
          Container(
            decoration: BoxDecoration(
              color: const Color(0xFF1C2530),
              borderRadius: BorderRadius.circular(16),
              border: Border.all(color: const Color(0xFF2A3540)),
            ),
            child: Row(
              children: [
                const SizedBox(width: 16),
                Icon(Icons.search, color: Colors.grey[500], size: 22),
                const SizedBox(width: 12),
                Expanded(
                  child: TextField(
                    controller: _controller,
                    style: const TextStyle(color: Colors.white, fontSize: 17),
                    decoration: InputDecoration(
                      hintText: '搜索股票  苹果 / AAPL / Tesla...',
                      hintStyle: TextStyle(color: Colors.grey[700], fontSize: 15),
                      border: InputBorder.none,
                      contentPadding: const EdgeInsets.symmetric(vertical: 16),
                    ),
                    onChanged: _onSearchChanged,
                    onSubmitted: (_) => _analyze(),
                  ),
                ),
                GestureDetector(
                  onTap: _loading ? null : _analyze,
                  child: Container(
                    margin: const EdgeInsets.all(6),
                    padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
                    decoration: BoxDecoration(
                      gradient: const LinearGradient(
                        colors: [Color(0xFF1D9BF0), Color(0xFF0969DA)],
                        begin: Alignment.topLeft,
                        end: Alignment.bottomRight,
                      ),
                      borderRadius: BorderRadius.circular(12),
                      boxShadow: [
                        BoxShadow(
                          color: const Color(0xFF1D9BF0).withAlpha(60),
                          blurRadius: 8,
                          offset: const Offset(0, 2),
                        ),
                      ],
                    ),
                    child: const Row(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Icon(Icons.auto_awesome, color: Colors.white, size: 18),
                        SizedBox(width: 6),
                        Text('分析', style: TextStyle(color: Colors.white, fontSize: 14, fontWeight: FontWeight.w600)),
                      ],
                    ),
                  ),
                ),
              ],
            ),
          ),
          if (_suggestions.isNotEmpty) _buildSuggestions(),
          const SizedBox(height: 12),
        ],
      ),
    );
  }

  Widget _buildSuggestions() {
    return Container(
      margin: const EdgeInsets.only(top: 4),
      decoration: BoxDecoration(
        color: const Color(0xFF1C2530),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: const Color(0xFF2A3540)),
      ),
      child: Column(
        children: _suggestions.map((match) => InkWell(
          onTap: () => _selectTicker(match),
          borderRadius: BorderRadius.circular(8),
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
            child: Row(
              children: [
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                  decoration: BoxDecoration(
                    color: const Color(0xFF1D9BF0).withAlpha(30),
                    borderRadius: BorderRadius.circular(6),
                  ),
                  child: Text(
                    match.symbol,
                    style: const TextStyle(color: Color(0xFF1D9BF0), fontSize: 14, fontWeight: FontWeight.bold),
                  ),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: Text(
                    match.name,
                    style: TextStyle(color: Colors.grey[300], fontSize: 14),
                    overflow: TextOverflow.ellipsis,
                  ),
                ),
                Text(
                  match.exchange,
                  style: TextStyle(color: Colors.grey[600], fontSize: 12),
                ),
              ],
            ),
          ),
        )).toList(),
      ),
    );
  }

  Widget _buildLoading() {
    return const Center(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          CircularProgressIndicator(color: Color(0xFF1D9BF0)),
          SizedBox(height: 16),
          Text('AI 正在分析中...', style: TextStyle(color: Colors.grey, fontSize: 16)),
          SizedBox(height: 8),
          Text('5位投资大师正在审阅数据', style: TextStyle(color: Colors.grey, fontSize: 14)),
        ],
      ),
    );
  }

  Widget _buildError() {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(32),
        child: Text(_error!, style: const TextStyle(color: Colors.redAccent, fontSize: 16)),
      ),
    );
  }

  Widget _buildEmpty() {
    return const Center(
      child: Text('输入股票代码开始分析', style: TextStyle(color: Colors.grey, fontSize: 16)),
    );
  }

  Widget _buildResult() {
    final r = _result!;
    return ListView(
      padding: const EdgeInsets.symmetric(horizontal: 16),
      children: [
        _buildConsensusCard(r),
        const SizedBox(height: 12),
        _buildSummaryCard(r),
        if (r.changes.hasChanges) ...[
          const SizedBox(height: 12),
          _buildChangesCard(r),
        ],
        const SizedBox(height: 12),
        _buildAgentsCard(r),
        const SizedBox(height: 32),
      ],
    );
  }

  Widget _buildConsensusCard(AnalysisResult r) {
    final color = switch (r.consensus.signal) {
      'bullish' => Colors.green,
      'bearish' => Colors.red,
      _ => Colors.grey,
    };

    return Card(
      color: const Color(0xFF1C2530),
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
      child: Padding(
        padding: const EdgeInsets.all(20),
        child: Column(
          children: [
            Text(r.ticker, style: const TextStyle(color: Colors.white, fontSize: 28, fontWeight: FontWeight.bold)),
            const SizedBox(height: 8),
            Text(r.date, style: TextStyle(color: Colors.grey[500], fontSize: 14)),
            const SizedBox(height: 16),
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 10),
              decoration: BoxDecoration(
                color: color.withOpacity(0.15),
                borderRadius: BorderRadius.circular(20),
                border: Border.all(color: color.withOpacity(0.5)),
              ),
              child: Text(
                '综合: ${r.consensus.signal == "bullish" ? "看多" : r.consensus.signal == "bearish" ? "看空" : "中性"} (${r.consensus.score.toStringAsFixed(2)})',
                style: TextStyle(color: color, fontSize: 18, fontWeight: FontWeight.bold),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildSummaryCard(AnalysisResult r) {
    return Card(
      color: const Color(0xFF1C2530),
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
      child: Padding(
        padding: const EdgeInsets.all(20),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Row(
              children: [
                Icon(Icons.chat_bubble_outline, color: Color(0xFF1D9BF0), size: 20),
                SizedBox(width: 8),
                Text('总结', style: TextStyle(color: Colors.white, fontSize: 16, fontWeight: FontWeight.w600)),
              ],
            ),
            const SizedBox(height: 12),
            Text(r.summary, style: TextStyle(color: Colors.grey[300], fontSize: 15, height: 1.6)),
          ],
        ),
      ),
    );
  }

  Widget _buildChangesCard(AnalysisResult r) {
    final changedAgents = r.changes.agentChanges.where((c) => c.changed).toList();

    return Card(
      color: const Color(0xFF2A1F1F),
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
      child: Padding(
        padding: const EdgeInsets.all(20),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Row(
              children: [
                Icon(Icons.change_circle_outlined, color: Colors.orange, size: 20),
                SizedBox(width: 8),
                Text('与上次对比', style: TextStyle(color: Colors.orange, fontSize: 16, fontWeight: FontWeight.w600)),
              ],
            ),
            const SizedBox(height: 12),
            ...changedAgents.map((c) => Padding(
              padding: const EdgeInsets.only(bottom: 8),
              child: Row(
                children: [
                  Expanded(child: Text(_agentDisplayName(c.agent), style: TextStyle(color: Colors.grey[400], fontSize: 14))),
                  SignalBadge(signal: c.from, size: 11),
                  const Padding(
                    padding: EdgeInsets.symmetric(horizontal: 6),
                    child: Icon(Icons.arrow_forward, color: Colors.grey, size: 14),
                  ),
                  SignalBadge(signal: c.to, size: 11),
                ],
              ),
            )),
          ],
        ),
      ),
    );
  }

  Widget _buildAgentsCard(AnalysisResult r) {
    return Card(
      color: const Color(0xFF1C2530),
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
      child: Padding(
        padding: const EdgeInsets.all(20),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text('各大师观点', style: TextStyle(color: Colors.white, fontSize: 16, fontWeight: FontWeight.w600)),
            const SizedBox(height: 16),
            ...r.agents.entries.map((e) => _buildAgentRow(e.key, e.value)),
          ],
        ),
      ),
    );
  }

  Widget _buildAgentRow(String agentId, AgentSignal signal) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Expanded(
                child: Text(
                  _agentDisplayName(agentId),
                  style: const TextStyle(color: Colors.white, fontSize: 15, fontWeight: FontWeight.w500),
                ),
              ),
              Text('${signal.confidence}%', style: TextStyle(color: Colors.grey[500], fontSize: 13)),
              const SizedBox(width: 8),
              SignalBadge(signal: signal.signal),
            ],
          ),
          const SizedBox(height: 6),
          Text(
            signal.reasoning,
            style: TextStyle(color: Colors.grey[400], fontSize: 13, height: 1.5),
          ),
          const Divider(color: Color(0xFF2A3540), height: 20),
        ],
      ),
    );
  }

  String _agentDisplayName(String id) {
    return switch (id) {
      'warren_buffett' => 'Warren Buffett',
      'cathie_wood' => 'Cathie Wood',
      'nassim_taleb' => 'Nassim Taleb',
      'stanley_druckenmiller' => 'Stanley Druckenmiller',
      'aswath_damodaran' => 'Aswath Damodaran',
      _ => id,
    };
  }
}
