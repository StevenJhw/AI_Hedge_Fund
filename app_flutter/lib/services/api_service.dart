import 'dart:async';
import 'dart:convert';
import 'package:http/http.dart' as http;
import '../models/analysis_result.dart';

class ApiService {
  static const _baseUrl = 'https://cymcihzlnonipcgrbkfo.supabase.co/functions/v1';
  static const _anonKey = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImN5bWNpaHpsbm9uaXBjZ3Jia2ZvIiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODAxMDgwMDQsImV4cCI6MjA5NTY4NDAwNH0.YiwllFbAxr2imxZtBaIUjUGTItueDzS87_n-TGlmrko';

  Future<AnalysisResult> analyzeStock(String ticker) async {
    final response = await http.post(
      Uri.parse('$_baseUrl/analyze-stock'),
      headers: {
        'Content-Type': 'application/json',
        'Authorization': 'Bearer $_anonKey',
      },
      body: jsonEncode({'ticker': ticker.toUpperCase()}),
    ).timeout(const Duration(seconds: 90));

    final body = utf8.decode(response.bodyBytes);

    if (response.statusCode == 422) {
      final error = jsonDecode(body);
      throw Exception(error['message'] ?? '股票代码无效或无数据');
    }

    if (response.statusCode == 500) {
      throw Exception('服务器内部错误，请稍后重试');
    }

    if (response.statusCode != 200) {
      final error = jsonDecode(body);
      throw Exception(error['message'] ?? error['error'] ?? '请求失败 (${response.statusCode})');
    }

    final json = jsonDecode(body);
    if (json == null || json['ticker'] == null) {
      throw const FormatException('返回数据格式异常');
    }

    return AnalysisResult.fromJson(json);
  }
}
