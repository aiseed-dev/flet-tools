import 'package:flet/flet.dart';

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
}
