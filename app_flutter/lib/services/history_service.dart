import 'dart:convert';
import 'package:http/http.dart' as http;
import '../models/history_item.dart';

class HistoryService {
  static const _baseUrl = 'https://cymcihzlnonipcgrbkfo.supabase.co/functions/v1';
  static const _anonKey = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImN5bWNpaHpsbm9uaXBjZ3Jia2ZvIiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODAxMDgwMDQsImV4cCI6MjA5NTY4NDAwNH0.YiwllFbAxr2imxZtBaIUjUGTItueDzS87_n-TGlmrko';

  Future<List<HistoryItem>> getHistory() async {
    final response = await http.post(
      Uri.parse('$_baseUrl/analyze-stock'),
      headers: {
        'Content-Type': 'application/json',
        'Authorization': 'Bearer $_anonKey',
      },
      body: jsonEncode({'action': 'get_history', 'limit': 50}),
    ).timeout(const Duration(seconds: 10));

    if (response.statusCode != 200) return [];

    final body = utf8.decode(response.bodyBytes);
    final data = jsonDecode(body);
    final list = data['history'] as List? ?? [];

    return list.map((e) => HistoryItem.fromJson({
      'id': e['id'],
      'ticker': e['ticker'],
      'date': e['analysis_date'],
      'signal': e['consensus_signal'],
      'score': e['consensus_score'],
      'summary': e['summary'] ?? '',
    })).toList();
  }

  Future<void> deleteItem(int id) async {
    await http.post(
      Uri.parse('$_baseUrl/analyze-stock'),
      headers: {
        'Content-Type': 'application/json',
        'Authorization': 'Bearer $_anonKey',
      },
      body: jsonEncode({'action': 'delete_history', 'id': id}),
    ).timeout(const Duration(seconds: 10));
  }
}
