// Renders every scene at the design's screen size and writes <out>/<scene>.png and <out>/<scene>.json (layout_dump.dart).
//
//   RENDER=1 [RENDER_OUT=build/app] [ONLY=settings_list,chat_card] flutter test test/render/render_scenes_test.dart
//
// Copy this file next to layout_dump.dart / render_support.dart (test/render/), then fill in `fonts`, `scenes` and the icon /
// spinner recognition. Scenes use fake services and the same sample data file as the board (see design-parity-flutter SKILL.md).
// Nothing here is a verdict: parity.py judges the JSON.
import 'dart:io';
import 'dart:ui' as ui;

import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter_test/flutter_test.dart';

import 'layout_dump.dart';
import 'render_support.dart';

// ── fill in ──────────────────────────────────────────────────────────────────────
/// The fonts the app draws with, loaded under the family names the theme uses. Use the SAME files the board's text was
/// measured with. (Fallback CJK/emoji fonts too, or those glyphs render as boxes.)
final fonts = <FontSpec>[
  // FontSpec('Roboto', 'fonts/NotoSansSC-Regular.otf'),
];

/// scene name (= the file name) -> the whole scene. Build it from the same sample data as the board.
final scenes = <String, Widget Function()>{
  // 'settings_list': () => const SettingsListScene(),
};

const dump = DumpOptions(iconFamilyPrefixes: ['AppIcons']);
const screen = Size(390, 844);
// ─────────────────────────────────────────────────────────────────────────────────

void main() {
  final enabled = Platform.environment['RENDER'] == '1';
  final out = Platform.environment['RENDER_OUT'] ?? 'build/app';
  final only = (Platform.environment['ONLY'] ?? '').split(',').where((s) => s.isNotEmpty).toSet();
  final dpr = double.tryParse(Platform.environment['RENDER_DPR'] ?? '') ?? 2;
  final captureRatio = double.tryParse(Platform.environment['RENDER_PNG_RATIO'] ?? '') ?? 1;

  setUpAll(() async {
    if (!enabled) return;
    await loadFonts(fonts, recordTo: '$out/fonts.json');
  });

  for (final entry in scenes.entries) {
    if (only.isNotEmpty && !only.contains(entry.key)) continue;
    testWidgets('render ${entry.key}', (tester) async {
      tester.view
        ..physicalSize = Size(screen.width * dpr, screen.height * dpr)
        ..devicePixelRatio = dpr;
      addTearDown(tester.view.reset);
      final semantics = tester.ensureSemantics();
      addTearDown(semantics.dispose);

      // an overflow is a finding, not a crash: collect it for the report
      final overflows = <String>[];
      final previous = FlutterError.onError;
      FlutterError.onError = (details) {
        final text = details.exceptionAsString();
        if (text.contains('overflowed')) {
          overflows.add(text.split('\n').first);
        } else {
          previous?.call(details);
        }
      };
      addTearDown(() => FlutterError.onError = previous);

      final boundary = GlobalKey();
      await tester.pumpWidget(
        RepaintBoundary(
          key: boundary,
          child: SizedBox(width: screen.width, height: screen.height, child: entry.value()),
        ),
      );
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 200));

      await dumpLayout(tester, '$out/${entry.key}.json', screen, scene: entry.key, overflows: overflows, options: dump);
      await tester.runAsync(() async {
        final ro = tester.renderObject<RenderRepaintBoundary>(find.byKey(boundary));
        final image = await ro.toImage(pixelRatio: captureRatio);
        final bytes = await image.toByteData(format: ui.ImageByteFormat.png);
        File('$out/${entry.key}.png')
          ..createSync(recursive: true)
          ..writeAsBytesSync(bytes!.buffer.asUint8List());
      });
    }, skip: !enabled);
  }
}
