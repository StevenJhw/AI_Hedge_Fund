import 'dart:convert';
import 'package:http/http.dart' as http;

class TickerMatch {
  final String symbol;
  final String name;
  final String exchange;

  TickerMatch({required this.symbol, required this.name, required this.exchange});
}

class TickerSearchService {
  Future<List<TickerMatch>> search(String query) async {
    if (query.trim().isEmpty) return [];

    final url = Uri.parse(
      'https://query2.finance.yahoo.com/v1/finance/search?q=${Uri.encodeComponent(query)}&quotesCount=6&newsCount=0&listsCount=0',
    );

    final response = await http.get(url, headers: {
      'User-Agent': 'Mozilla/5.0',
    }).timeout(const Duration(seconds: 5));

    if (response.statusCode != 200) return [];

    final data = jsonDecode(response.body);
    final quotes = data['quotes'] as List? ?? [];

    return quotes
        .where((q) => q['quoteType'] == 'EQUITY')
        .map((q) => TickerMatch(
              symbol: q['symbol'] ?? '',
              name: q['shortname'] ?? q['longname'] ?? '',
              exchange: q['exchange'] ?? '',
            ))
        .toList();
  }
}
