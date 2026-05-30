class HistoryItem {
  final int? id;
  final String ticker;
  final String date;
  final String signal;
  final double score;
  final String summary;

  HistoryItem({
    this.id,
    required this.ticker,
    required this.date,
    required this.signal,
    required this.score,
    required this.summary,
  });

  factory HistoryItem.fromJson(Map<String, dynamic> json) {
    return HistoryItem(
      id: json['id'],
      ticker: json['ticker'] ?? '',
      date: json['date'] ?? '',
      signal: json['signal'] ?? 'neutral',
      score: (json['score'] ?? 0).toDouble(),
      summary: json['summary'] ?? '',
    );
  }
}
