import 'dart:convert';

import 'package:flet/flet.dart';
import 'package:flutter/foundation.dart';
import 'package:printing/printing.dart';

/// Non-visual service wrapping the `printing` package:
/// native print dialog / share sheet for PDF documents.
class PrintingService extends FletService {
  PrintingService({required super.control});

  @override
  void init() {
    super.init();
    debugPrint("Printing(${control.id}).init");
    control.addInvokeMethodListener(_invokeMethod);
  }

  /// PDF bytes arrive either as raw binary (msgpack) or base64 string.
  Uint8List _pdfBytes(dynamic value) {
    if (value is Uint8List) return value;
    if (value is List<int>) return Uint8List.fromList(value);
    if (value is String) return base64Decode(value);
    throw Exception("printing: unsupported pdf argument type: "
        "${value.runtimeType}");
  }

  Future<dynamic> _invokeMethod(String name, dynamic args) async {
    debugPrint("Printing.$name()");
    switch (name) {
      case "print_pdf":
        final pdf = _pdfBytes(args["pdf"]);
        return Printing.layoutPdf(
            onLayout: (format) async => pdf,
            name: args["name"] as String? ?? "document");
      case "share_pdf":
        final pdf = _pdfBytes(args["pdf"]);
        return Printing.sharePdf(
            bytes: pdf,
            filename: args["filename"] as String? ?? "document.pdf");
      default:
        throw Exception("Unknown Printing method: $name");
    }
  }

  @override
  void dispose() {
    debugPrint("Printing(${control.id}).dispose");
    control.removeInvokeMethodListener(_invokeMethod);
    super.dispose();
  }
}
