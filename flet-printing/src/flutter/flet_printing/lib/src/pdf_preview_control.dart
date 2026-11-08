import 'package:flet/flet.dart';
// printing's PdfPreview is written against the Flutter SDK's Material library,
// but since Flet 1.1 an app only provides material_ui ancestors (Theme,
// Material, MaterialLocalizations), which the SDK widgets do not see. So this
// control supplies the SDK ones itself, with colors taken from the app's
// current material_ui theme. Drop this once printing moves to material_ui.
import 'package:flutter/material.dart' as sdk;
import 'package:flutter/widgets.dart';
import 'package:material_ui/material_ui.dart' as mui;
import 'package:printing/printing.dart';

/// Visual PDF preview with built-in print/share actions
/// (wraps `printing`'s PdfPreview widget).
class PdfPreviewControl extends StatelessWidget {
  final Control control;

  const PdfPreviewControl({super.key, required this.control});

  /// The app's material_ui color scheme, rebuilt as an SDK theme.
  static sdk.ThemeData _sdkTheme(BuildContext context) {
    final c = mui.Theme.of(context).colorScheme;
    return sdk.ThemeData.from(
      colorScheme: sdk.ColorScheme(
        brightness: c.brightness,
        primary: c.primary,
        onPrimary: c.onPrimary,
        primaryContainer: c.primaryContainer,
        onPrimaryContainer: c.onPrimaryContainer,
        secondary: c.secondary,
        onSecondary: c.onSecondary,
        tertiary: c.tertiary,
        onTertiary: c.onTertiary,
        error: c.error,
        onError: c.onError,
        surface: c.surface,
        onSurface: c.onSurface,
        onSurfaceVariant: c.onSurfaceVariant,
        surfaceContainerHighest: c.surfaceContainerHighest,
        outline: c.outline,
        outlineVariant: c.outlineVariant,
        inverseSurface: c.inverseSurface,
        onInverseSurface: c.onInverseSurface,
        inversePrimary: c.inversePrimary,
        shadow: c.shadow,
        scrim: c.scrim,
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final resolvedSrc = control.getSrc("src");
    if (resolvedSrc.error != null) {
      throw Exception("PdfPreview src decode error: ${resolvedSrc.error}");
    }
    final bytes = resolvedSrc.bytes;
    if (bytes == null) {
      throw Exception(
          "PdfPreview must have \"src\" specified as PDF bytes or base64.");
    }

    final preview = PdfPreview(
      build: (format) async => bytes,
      allowPrinting: control.getBool("allow_printing", true)!,
      allowSharing: control.getBool("allow_sharing", true)!,
      canChangePageFormat: control.getBool("can_change_page_format", false)!,
      canChangeOrientation: control.getBool("can_change_orientation", false)!,
      canDebug: false,
      useActions: control.getBool("use_actions", true)!,
      pdfFileName: control.getString("pdf_file_name"),
      onPrinted: (context) => control.triggerEvent("printed"),
      onShared: (context) => control.triggerEvent("shared"),
    );

    return LayoutControl(
      control: control,
      child: Localizations.override(
        context: context,
        delegates: const [sdk.DefaultMaterialLocalizations.delegate],
        child: sdk.Theme(
          data: _sdkTheme(context),
          child: sdk.Material(
              type: sdk.MaterialType.transparency, child: preview),
        ),
      ),
    );
  }
}
