// The app's text engine answers the board's questions: how wide is this string, where does it wrap, where does the
// ellipsis fall, where is the baseline of a line box. The board (kit.MeasuredRuler) reads the answers, so its wraps,
// bubble widths and baselines are the app's, not an estimate.
//
//   python3 build_board.py --measured build/measured_text.json --needed build/needed_text.json   # lists what is missing
//   MEASURE=1 flutter test test/render/measure_text_test.dart                                      # answers it
//   python3 build_board.py --measured build/measured_text.json ...                                 # uses the answers
// Repeat until the board prints "0 strings still estimated" (two rounds are usual).
//
// Copy next to render_support.dart; set `fonts`, `sans`, `mono` exactly as in render_scenes_test.dart and the theme.
import 'dart:convert';
import 'dart:io';

import 'package:flutter/painting.dart';
import 'package:flutter_test/flutter_test.dart';

import 'render_support.dart';

// ── fill in (same values as the render test and the app's theme) ────────────────────
const fonts = <FontSpec>[
  // FontSpec('Roboto', 'fonts/NotoSansSC-Regular.otf'),
];
const sans = 'Roboto';
const mono = 'monospace';
// ─────────────────────────────────────────────────────────────────────────────────

String g(num v) => v == v.roundToDouble() ? v.toInt().toString() : v.toString();

String key(num size, int weight, bool isMono, [List<Object> rest = const []]) =>
    [g(size), weight, isMono ? 1 : 0, ...rest].join('|');

TextStyle style(num size, int weight, bool isMono, {num? lh}) => TextStyle(
      fontFamily: isMono ? mono : sans,
      fontSize: size.toDouble(),
      fontWeight: FontWeight.values[(weight ~/ 100) - 1],
      height: lh == null ? null : lh / size,
      leadingDistribution: TextLeadingDistribution.even,
    );

TextPainter layout(String s, TextStyle st, {double? maxWidth}) =>
    TextPainter(text: TextSpan(text: s, style: st), textDirection: TextDirection.ltr)..layout(maxWidth: maxWidth ?? double.infinity);

List<String> wrapLines(String s, TextStyle st, double maxw) {
  final tp = layout(s, st, maxWidth: maxw);
  final out = <String>[];
  var pos = 0;
  for (var i = 0; i < tp.computeLineMetrics().length && pos < s.length; i++) {
    final end = tp.getLineBoundary(TextPosition(offset: pos)).end;
    if (end <= pos) break;
    out.add(s.substring(pos, end).replaceAll('\n', '').trim());
    pos = end;
  }
  return out;
}

String ellipsize(String s, TextStyle st, double maxw) {
  if (layout(s, st).width <= maxw) return s;
  var lo = 0, hi = s.length;
  while (lo < hi) {
    final mid = (lo + hi + 1) ~/ 2;
    if (layout('${s.substring(0, mid)}…', st).width <= maxw) {
      lo = mid;
    } else {
      hi = mid - 1;
    }
  }
  return '${s.substring(0, lo)}…';
}

void main() {
  final enabled = Platform.environment['MEASURE'] == '1';
  final neededPath = Platform.environment['NEEDED'] ?? 'build/needed_text.json';
  final outPath = Platform.environment['MEASURED_OUT'] ?? 'build/measured_text.json';

  // fonts are loaded outside the test's fake-async zone (recording their sha256 needs a real process)
  setUpAll(() async {
    if (!enabled) return;
    await loadFonts(fonts, recordTo: outPath.replaceFirst(RegExp(r'[^/]+$'), 'measure_fonts.json'));
  });

  testWidgets('measure the text the board asks for', (tester) async {
    final needed = jsonDecode(File(neededPath).readAsStringSync()) as Map<String, dynamic>;
    final prior = File(outPath).existsSync() ? jsonDecode(File(outPath).readAsStringSync()) as Map<String, dynamic> : <String, dynamic>{};
    Map<String, dynamic> bucket(String k) => (prior[k] as Map<String, dynamic>?) ?? <String, dynamic>{};
    final width = bucket('width'), wrap = bucket('wrap'), baseline = bucket('baseline'), ell = bucket('ellipsis');

    for (final r in (needed['width'] as List? ?? [])) {
      final st = style(r['size'], r['weight'], r['mono']);
      width[key(r['size'], r['weight'], r['mono'], [r['s']])] = layout(r['s'], st).width;
    }
    for (final r in (needed['wrap'] as List? ?? [])) {
      final st = style(r['size'], r['weight'], r['mono']);
      wrap[key(r['size'], r['weight'], r['mono'], [g(r['maxw']), r['s']])] = wrapLines(r['s'], st, (r['maxw'] as num).toDouble());
    }
    for (final r in (needed['ellipsis'] as List? ?? [])) {
      final st = style(r['size'], r['weight'], r['mono']);
      ell[key(r['size'], r['weight'], r['mono'], [g(r['maxw']), r['s']])] = ellipsize(r['s'], st, (r['maxw'] as num).toDouble());
    }
    for (final r in (needed['baseline'] as List? ?? [])) {
      final st = style(r['size'], r['weight'], r['mono'], lh: r['lh']);
      final tp = layout('Hg中', st);
      // the box of a line of this style must be exactly `lh` tall, or baseline-from-top is not the whole story
      expect(tp.height, closeTo((r['lh'] as num).toDouble(), 0.01), reason: 'style ${r['size']}/${r['weight']} lh ${r['lh']}');
      baseline[key(r['size'], r['weight'], r['mono'], [g(r['lh'])])] =
          tp.computeDistanceToActualBaseline(TextBaseline.alphabetic);
    }
    File(outPath)
      ..createSync(recursive: true)
      ..writeAsStringSync(const JsonEncoder.withIndent(' ').convert({
        'meta': {'engine': Platform.version, 'about': 'measured by the app text engine (measure_text_test.dart)'},
        'width': width,
        'wrap': wrap,
        'baseline': baseline,
        'ellipsis': ell,
      }));
  }, skip: !enabled);
}
