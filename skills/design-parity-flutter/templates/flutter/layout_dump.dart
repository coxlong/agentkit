// Writes what the widgets actually draw, as JSON in logical pixels of the screen: the app side of the parity check.
//
//   texts  id, s, l t w h, bl (first baseline), ll lw (first line's left edge and width), lines, fs fw c a ff lh ls,
//          align, maxLines, ellipsis (the text was cut by maxLines / ellipsis)
//   icons  id, cp (code point), ff (font family = stroke weight), size, cx cy, c a
//   boxes  id, k, l t w h, c a, circle/pill, r{tl tr bl br}, border{c w}, shadows[{dx dy blur spread c a}]
//   invariants  overflows (RenderFlex overflow messages), taps (semantics nodes with a tap action), coverage (how many
//          of the drawn texts / icons / boxes carry an id), idConflicts
//
// IDs come from the widgets: give a widget `key: ValueKey('row/1/title')` and the first Text / Icon glyph / decorated
// box inside it is exported with that id. The parity check pairs it with the design element
// "<screen>/row/1/title". Nothing here knows about the app: pass how to recognise an icon font and a spinner.
import 'dart:convert';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter_test/flutter_test.dart';

class DumpOptions {
  const DumpOptions({this.iconFamilyPrefixes = const ['AppIcons', 'MaterialIcons'], this.isSpinner});

  /// A Text whose font family starts with one of these is an icon glyph (its code point is exported).
  final List<String> iconFamilyPrefixes;

  /// Spinners are painted, not glyphs: say which widgets they are and they are exported as icons with `spinner: true`.
  final bool Function(Widget widget)? isSpinner;
}

String _hex(Color c) => '#${(c.toARGB32() & 0xFFFFFF).toRadixString(16).padLeft(6, '0').toUpperCase()}';

double _r(num v) => (v * 100).round() / 100;

double _baseline(RenderBox box) =>
    // ignore: invalid_use_of_protected_member, invalid_use_of_visible_for_overriding_member
    box.computeDistanceToActualBaseline(TextBaseline.alphabetic) ?? 0;

Map<String, dynamic>? _radius(BorderRadiusGeometry? radius) {
  if (radius is BorderRadius) {
    return {
      'tl': _r(radius.topLeft.x),
      'tr': _r(radius.topRight.x),
      'bl': _r(radius.bottomLeft.x),
      'br': _r(radius.bottomRight.x),
    };
  }
  return null;
}

({double left, double width, int lines}) _firstLine(List<TextBox> boxes, double fallbackWidth) {
  if (boxes.isEmpty) return (left: 0, width: fallbackWidth, lines: 1);
  final top = boxes.first.top;
  final line = boxes.where((b) => (b.top - top).abs() < 1).toList();
  final left = line.map((b) => b.left).reduce((a, b) => a < b ? a : b);
  final right = line.map((b) => b.right).reduce((a, b) => a > b ? a : b);
  return (left: left, width: right - left, lines: {for (final b in boxes) b.top.round()}.length);
}

String _align(TextAlign a) => switch (a) {
      TextAlign.center => 'middle',
      TextAlign.end || TextAlign.right => 'end',
      _ => 'start',
    };

bool _isMeasured(RenderObject o) {
  if (o is RenderParagraph || o is RenderEditable || o is RenderPhysicalModel || o is RenderPhysicalShape) return true;
  if (o is RenderDecoratedBox) {
    final d = o.decoration;
    return d is BoxDecoration && (d.color != null || d.border != null || (d.boxShadow?.isNotEmpty ?? false));
  }
  return false;
}

RenderObject? _firstMeasured(RenderObject o) {
  if (_isMeasured(o)) return o;
  RenderObject? found;
  o.visitChildren((c) => found ??= _firstMeasured(c));
  return found;
}

/// Collects every visible text, icon and filled box under the first RepaintBoundary of [rootElement]'s tree.
Map<String, dynamic> collectLayout(Element rootElement, Size screen, {DumpOptions options = const DumpOptions()}) {
  final texts = <Map<String, dynamic>>[];
  final icons = <Map<String, dynamic>>[];
  final boxes = <Map<String, dynamic>>[];
  final conflicts = <String>[];
  final view = Offset.zero & screen;

  // id of the render object a keyed widget draws
  final ids = <RenderObject, String>{};
  void walkIds(Element e) {
    final key = e.widget.key;
    if (key is ValueKey<String>) {
      final ro = e.renderObject;
      final target = ro == null ? null : _firstMeasured(ro);
      if (target != null) {
        if (ids.containsKey(target) && ids[target] != key.value) {
          conflicts.add('${key.value} and ${ids[target]} draw the same render object; key the inner widget only');
        } else {
          ids[target] = key.value;
        }
      }
    }
    e.visitChildren(walkIds);
  }

  walkIds(rootElement);

  bool visible(Rect r) => r.overlaps(view) && r.width > 0 && r.height > 0;

  List<Map<String, dynamic>> shadows(List<BoxShadow>? list) => [
        for (final s in list ?? const <BoxShadow>[])
          {
            'dx': _r(s.offset.dx),
            'dy': _r(s.offset.dy),
            'blur': _r(s.blurRadius),
            'spread': _r(s.spreadRadius),
            'c': _hex(s.color),
            'a': _r(s.color.a),
          },
      ];

  void addMaterial(RenderBox box, Color color, Object? radius, bool circle, bool pill) {
    final rect = box.localToGlobal(Offset.zero) & box.size;
    if (!visible(rect) || color.a == 0) return;
    boxes.add({
      'id': ids[box],
      'k': 'material',
      'l': _r(rect.left),
      't': _r(rect.top),
      'w': _r(rect.width),
      'h': _r(rect.height),
      'c': _hex(color),
      'a': _r(color.a),
      'circle': circle,
      'pill': pill,
      'r': radius,
    });
  }

  void visit(RenderObject o) {
    if (o is RenderOffstage && o.offstage) return;
    if (o is RenderOpacity && o.opacity == 0) return;
    if (o is RenderParagraph) {
      final span = o.text;
      final text = span.toPlainText();
      final style = span is TextSpan ? span.style : null;
      final rect = o.localToGlobal(Offset.zero) & o.size;
      if (text.trim().isNotEmpty && visible(rect)) {
        final family = style?.fontFamily;
        if (family != null && options.iconFamilyPrefixes.any(family.startsWith)) {
          icons.add({
            'id': ids[o],
            'cp': text.codeUnitAt(0),
            'ff': family,
            'size': _r(style?.fontSize ?? 0),
            'cx': _r(rect.center.dx),
            'cy': _r(rect.center.dy),
            'c': style?.color == null ? null : _hex(style!.color!),
            'a': style?.color == null ? null : _r(style!.color!.a),
          });
        } else {
          final info = _firstLine(
            o.getBoxesForSelection(TextSelection(baseOffset: 0, extentOffset: text.length)),
            rect.width,
          );
          texts.add({
            'id': ids[o],
            's': text,
            'l': _r(rect.left),
            't': _r(rect.top),
            'w': _r(rect.width),
            'h': _r(rect.height),
            'bl': _r(rect.top + _baseline(o)),
            'll': _r(rect.left + info.left),
            'lw': _r(info.width),
            'lines': info.lines,
            'fs': style?.fontSize,
            'fw': style?.fontWeight?.value,
            'c': style?.color == null ? null : _hex(style!.color!),
            'a': style?.color == null ? null : _r(style!.color!.a),
            'ff': style?.fontFamily,
            'lh': style?.height,
            'ls': style?.letterSpacing,
            'align': _align(o.textAlign),
            'maxLines': o.maxLines,
            'ellipsis': o.overflow == TextOverflow.ellipsis && o.didExceedMaxLines,
          });
        }
      }
    } else if (o is RenderEditable) {
      final span = o.text;
      final rect = o.localToGlobal(Offset.zero) & o.size;
      if (span != null && visible(rect)) {
        final style = span.style;
        final text = span.toPlainText();
        final info = _firstLine(
          o.getBoxesForSelection(TextSelection(baseOffset: 0, extentOffset: text.length)),
          rect.width,
        );
        texts.add({
          'id': ids[o],
          's': text,
          'l': _r(rect.left),
          't': _r(rect.top),
          'w': _r(rect.width),
          'h': _r(rect.height),
          'bl': _r(rect.top + _baseline(o)),
          'll': _r(rect.left + info.left),
          'lw': _r(info.width),
          'lines': info.lines,
          'fs': style?.fontSize,
          'fw': style?.fontWeight?.value,
          'c': style?.color == null ? null : _hex(style!.color!),
          'a': style?.color == null ? null : _r(style!.color!.a),
          'ff': style?.fontFamily,
          'lh': style?.height,
          'ls': style?.letterSpacing,
          'align': _align(o.textAlign),
          'maxLines': o.maxLines,
          'ellipsis': false,
          'editable': true,
        });
      }
    } else if (o is RenderDecoratedBox) {
      final d = o.decoration;
      final rect = o.localToGlobal(Offset.zero) & o.size;
      if (d is BoxDecoration && visible(rect) && (d.color != null || d.border != null || (d.boxShadow?.isNotEmpty ?? false))) {
        final b = d.border;
        boxes.add({
          'id': ids[o],
          'k': 'deco',
          'l': _r(rect.left),
          't': _r(rect.top),
          'w': _r(rect.width),
          'h': _r(rect.height),
          'c': d.color == null ? null : _hex(d.color!),
          'a': d.color == null ? null : _r(d.color!.a),
          'circle': d.shape == BoxShape.circle,
          'r': _radius(d.borderRadius),
          'border': b is Border && b.top.style != BorderStyle.none && b.top.width > 0
              ? {'c': _hex(b.top.color), 'w': _r(b.top.width)}
              : null,
          'shadows': shadows(d.boxShadow),
        });
      }
    } else if (o is RenderPhysicalModel) {
      addMaterial(o, o.color, _radius(o.borderRadius), o.shape == BoxShape.circle, false);
    } else if (o is RenderPhysicalShape) {
      Object? radius;
      var circle = false;
      var pill = false;
      final clipper = o.clipper;
      if (clipper is ShapeBorderClipper) {
        final shape = clipper.shape;
        if (shape is RoundedRectangleBorder) {
          radius = _radius(shape.borderRadius);
        } else if (shape is StadiumBorder) {
          pill = true;
        } else if (shape is CircleBorder) {
          circle = true;
        }
      }
      addMaterial(o, o.color, radius, circle, pill);
    }
    o.visitChildren(visit);
  }

  // the first RepaintBoundary is the scene's own (the test wraps the scene in one)
  Element? boundary;
  void findBoundary(Element e) {
    if (boundary != null) return;
    if (e.widget is RepaintBoundary) {
      boundary = e;
      return;
    }
    e.visitChildren(findBoundary);
  }

  findBoundary(rootElement);
  visit((boundary ?? rootElement).renderObject!);

  // spinners are painted: export them as icons of their size
  if (options.isSpinner != null) {
    void walkSpinners(Element e) {
      if (options.isSpinner!(e.widget)) {
        final box = e.renderObject;
        if (box is RenderBox && box.hasSize) {
          final rect = box.localToGlobal(Offset.zero) & box.size;
          if (rect.overlaps(view)) {
            icons.add({
              'id': (e.widget.key is ValueKey<String>) ? (e.widget.key! as ValueKey<String>).value : null,
              'cp': 0,
              'spinner': true,
              'size': _r(rect.width),
              'cx': _r(rect.center.dx),
              'cy': _r(rect.center.dy),
            });
          }
        }
      }
      e.visitChildren(walkSpinners);
    }

    walkSpinners(rootElement);
  }

  Map<String, int> cov(List<Map<String, dynamic>> l) => {
        'tagged': l.where((e) => e['id'] != null && e['spinner'] != true).length,
        'total': l.where((e) => e['spinner'] != true).length,
      };
  return {
    'texts': texts,
    'icons': icons,
    'boxes': boxes,
    'invariants': {
      'coverage': {'texts': cov(texts), 'icons': cov(icons), 'boxes': cov(boxes)},
      'idConflicts': conflicts,
    },
  };
}

/// Semantics nodes with a tap action, in logical pixels. The test must hold `tester.ensureSemantics()`.
List<Map<String, dynamic>> collectTaps(WidgetTester tester) {
  // semantics live on the view's own PipelineOwner (not on the root one) since multi-view
  final root = tester.binding.renderViews.first.owner?.semanticsOwner?.rootSemanticsNode;
  if (root == null) return [];
  final dpr = tester.view.devicePixelRatio;
  final taps = <Map<String, dynamic>>[];
  void visit(SemanticsNode node) {
    final data = node.getSemanticsData();
    if (data.hasAction(SemanticsAction.tap) && !node.isInvisible) {
      var rect = node.rect;
      SemanticsNode? n = node;
      while (n != null) {
        final t = n.transform;
        if (t != null) rect = MatrixUtils.transformRect(t, rect);
        n = n.parent;
      }
      taps.add({
        'id': data.identifier.isEmpty ? null : data.identifier,
        'label': data.label,
        'l': _r(rect.left / dpr),
        't': _r(rect.top / dpr),
        'w': _r(rect.width / dpr),
        'h': _r(rect.height / dpr),
      });
    }
    node.visitChildren((c) {
      visit(c);
      return true;
    });
  }

  visit(root);
  return taps;
}

/// Writes the layout of the scene on screen to [path] (JSON), with the invariants.
Future<void> dumpLayout(
  WidgetTester tester,
  String path,
  Size screen, {
  String scene = '',
  List<String> overflows = const [],
  DumpOptions options = const DumpOptions(),
}) async {
  final data = collectLayout(tester.binding.rootElement!, screen, options: options);
  final inv = data['invariants'] as Map<String, dynamic>;
  inv['overflows'] = overflows;
  inv['taps'] = collectTaps(tester);
  data['scene'] = scene;
  data['screen_size'] = [screen.width, screen.height];
  File(path)
    ..createSync(recursive: true)
    ..writeAsStringSync(const JsonEncoder.withIndent(' ').convert(data));
}
