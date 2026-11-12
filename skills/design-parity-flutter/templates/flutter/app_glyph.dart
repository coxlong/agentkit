import 'package:flutter/widgets.dart';

import 'design_tokens.g.dart';

/// One icon of the board in every stroke weight it can be drawn with (generated: app_icons.g.dart).
///
/// A font glyph has one stroke width, so the board's rule "stroke by size" (tokens scales.icon_stroke_units) becomes
/// "weight font by size": [at] picks the font whose stroke gives the board's stroke for that size.
@immutable
class AppGlyph {
  const AppGlyph(this.byWeight);

  final Map<int, IconData> byWeight;

  IconData at(double size) => byWeight[DesignTokens.iconWeight(size)]!;
}
