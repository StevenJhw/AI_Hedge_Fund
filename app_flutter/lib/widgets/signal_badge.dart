import 'package:flutter/material.dart';

class SignalBadge extends StatelessWidget {
  final String signal;
  final double size;

  const SignalBadge({super.key, required this.signal, this.size = 12});

  @override
  Widget build(BuildContext context) {
    final color = switch (signal) {
      'bullish' => Colors.green,
      'bearish' => Colors.red,
      _ => Colors.grey,
    };
    final label = switch (signal) {
      'bullish' => '看多',
      'bearish' => '看空',
      _ => '中性',
    };

    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
      decoration: BoxDecoration(
        color: color.withOpacity(0.15),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: color.withOpacity(0.5)),
      ),
      child: Text(
        label,
        style: TextStyle(color: color, fontSize: size, fontWeight: FontWeight.w600),
      ),
    );
  }
}
