import 'package:flutter/widgets.dart';

import 'app_glyph.dart';

export 'app_glyph.dart';
export 'app_icons.g.dart';

/// An icon of the board's set drawn at [size] in the stroke weight the board uses for that size.
/// [size] has no default so that every use says which board size it is (12, 16, 20, 24 ...).
class AppIcon extends StatelessWidget {
  const AppIcon(this.glyph, {super.key, required this.size, this.color, this.semanticLabel});

  final AppGlyph glyph;
  final double size;
  final Color? color;
  final String? semanticLabel;

  @override
  Widget build(BuildContext context) =>
      Icon(glyph.at(size), size: size, color: color, semanticLabel: semanticLabel);
}
