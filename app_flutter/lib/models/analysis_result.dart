class AgentSignal {
  final String signal;
  final int confidence;
  final String reasoning;

  AgentSignal({
    required this.signal,
    required this.confidence,
    required this.reasoning,
  });

  factory AgentSignal.fromJson(Map<String, dynamic> json) {
    return AgentSignal(
      signal: json['signal'] ?? 'neutral',
      confidence: (json['confidence'] ?? 50).toInt(),
      reasoning: json['reasoning'] ?? '',
    );
  }

  bool get isBullish => signal == 'bullish';
  bool get isBearish => signal == 'bearish';
  bool get isNeutral => signal == 'neutral';
}

class Consensus {
  final String signal;
  final double score;

  Consensus({required this.signal, required this.score});

  factory Consensus.fromJson(Map<String, dynamic> json) {
    return Consensus(
      signal: json['signal'] ?? 'neutral',
      score: (json['score'] ?? 0).toDouble(),
    );
  }
}

class AgentChange {
  final String agent;
  final String from;
  final String to;
  final int confidenceChange;
  final bool changed;

  AgentChange({
    required this.agent,
    required this.from,
    required this.to,
    required this.confidenceChange,
    required this.changed,
  });

  factory AgentChange.fromJson(Map<String, dynamic> json) {
    return AgentChange(
      agent: json['agent'] ?? '',
      from: json['from'] ?? '',
      to: json['to'] ?? '',
      confidenceChange: (json['confidence_change'] ?? 0).toInt(),
      changed: json['changed'] ?? false,
    );
  }
}

class Changes {
  final bool hasPrevious;
  final bool consensusChanged;
  final String? consensusFrom;
  final String? consensusTo;
  final double? scoreChange;
  final List<AgentChange> agentChanges;
  final String summary;

  Changes({
    required this.hasPrevious,
    required this.consensusChanged,
    this.consensusFrom,
    this.consensusTo,
    this.scoreChange,
    required this.agentChanges,
    required this.summary,
  });

  factory Changes.fromJson(Map<String, dynamic> json) {
    return Changes(
      hasPrevious: json['has_previous'] ?? false,
      consensusChanged: json['consensus_changed'] ?? false,
      consensusFrom: json['consensus_from'],
      consensusTo: json['consensus_to'],
      scoreChange: json['score_change']?.toDouble(),
      agentChanges: (json['agent_changes'] as List? ?? [])
          .map((e) => AgentChange.fromJson(e))
          .toList(),
      summary: json['summary'] ?? '',
    );
  }

  bool get hasChanges => hasPrevious && agentChanges.any((c) => c.changed);
}

class AnalysisResult {
  final String ticker;
  final String date;
  final String summary;
  final Map<String, AgentSignal> agents;
  final Consensus consensus;
  final Changes changes;

  AnalysisResult({
    required this.ticker,
    required this.date,
    required this.summary,
    required this.agents,
    required this.consensus,
    required this.changes,
  });

  factory AnalysisResult.fromJson(Map<String, dynamic> json) {
    final agentsMap = <String, AgentSignal>{};
    if (json['agents'] != null) {
      (json['agents'] as Map<String, dynamic>).forEach((key, value) {
        agentsMap[key] = AgentSignal.fromJson(value);
      });
    }

    return AnalysisResult(
      ticker: json['ticker'] ?? '',
      date: json['date'] ?? '',
      summary: json['summary'] ?? '',
      agents: agentsMap,
      consensus: Consensus.fromJson(json['consensus'] ?? {}),
      changes: Changes.fromJson(json['changes'] ?? {}),
    );
  }
}
