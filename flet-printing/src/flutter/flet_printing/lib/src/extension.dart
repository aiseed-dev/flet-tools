import 'package:flet/flet.dart';
import 'package:flutter/widgets.dart';

import 'pdf_preview_control.dart';
import 'printing_service.dart';

class Extension extends FletExtension {
  @override
  FletService? createService(Control control) {
    switch (control.type) {
      case "Printing":
        return PrintingService(control: control);
      default:
        return null;
    }
  }

  @override
  Widget? createWidget(Key? key, Control control) {
    switch (control.type) {
      case "PdfPreview":
        return PdfPreviewControl(key: key, control: control);
      default:
        return null;
    }
  }
}
