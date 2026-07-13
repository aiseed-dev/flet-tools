import 'package:flet/flet.dart';
import 'package:flutter/material.dart';
import 'package:printing/printing.dart';

/// Visual PDF preview with built-in print/share actions
/// (wraps `printing`'s PdfPreview widget).
class PdfPreviewControl extends StatelessWidget {
  final Control control;

  const PdfPreviewControl({super.key, required this.control});

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

    return LayoutControl(control: control, child: preview);
  }
}
