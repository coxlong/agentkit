// Shared by the render test and the text-measure test: the SAME font files in both, so the board is measured with the
// text engine that draws the app.
import 'dart:convert';
import 'dart:io';

import 'package:flutter/services.dart';

class FontSpec {
  const FontSpec(this.family, this.path);
  final String family;
  final String path;
}

/// Registers [fonts] with the test engine (a family may list several files: regular, bold, ...) and writes
/// {family, path, sha256} for each file to [recordTo], so a report says exactly which fonts the numbers came from.
Future<void> loadFonts(List<FontSpec> fonts, {String? recordTo}) async {
  final byFamily = <String, List<String>>{};
  for (final f in fonts) {
    byFamily.putIfAbsent(f.family, () => []).add(f.path);
  }
  for (final e in byFamily.entries) {
    final loader = FontLoader(e.key);
    for (final p in e.value) {
      loader.addFont(Future.value(ByteData.sublistView(File(p).readAsBytesSync())));
    }
    await loader.load();
  }
  if (recordTo != null) {
    final rows = <Map<String, String>>[];
    for (final f in fonts) {
      final r = await Process.run('sha256sum', [f.path]);
      rows.add({'family': f.family, 'path': f.path, 'sha256': (r.stdout as String).split(' ').first});
    }
    File(recordTo)
      ..createSync(recursive: true)
      ..writeAsStringSync(const JsonEncoder.withIndent(' ').convert(rows));
  }
}
