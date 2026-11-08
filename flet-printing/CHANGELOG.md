# Changelog

## 0.3.0 (unreleased)

- **Flet 1.1.** Requires `flet>=1.1.0` (Dart `flet: ^1.1.0`, Flutter 3.47).
  0.2.0 was built against Flet 0.85 and does not build with Flet 1.x.
- `PdfPreview` keeps working although Flet 1.1 moved Material to
  `material_ui`: `printing`'s preview widget still uses the Flutter SDK's
  Material, so the control now supplies the SDK `Theme`, `Material` and
  `MaterialLocalizations` itself, with colors from the app's theme.
- `printing` ^5.15.1 (iOS/macOS crash fixes, pdf.js security update).

## 0.2.0 (2026-07-14)

- **PdfPreview visual control** — display a PDF (scrollable pages) with
  built-in print/share action buttons. Wraps `printing`'s `PdfPreview`
  widget. Together with the `Printing` service this answers
  [flet-dev/flet#894](https://github.com/flet-dev/flet/issues/894) in
  full — the 2023 request asked to "display a PDF in a widget that
  allows printing or saving it".
  - `src` (PDF bytes or base64), `allow_printing`, `allow_sharing`,
    `use_actions`, `pdf_file_name`, `on_printed`/`on_shared` events
  - `can_change_page_format`/`can_change_orientation` are off by
    default: the PDF passed in is already laid out
- Version is now dynamic (single source: `flet_printing.__version__`).
- Verified: `flutter analyze` clean, `flet build linux` succeeds with
  the widget registered, built binary runs 15s with zero exceptions,
  wheel packaging includes the `flutter/` directory.

## 0.1.0 (2026-07-14)

- Initial release: `Printing` service (`print_pdf` with native print
  dialog and cancel detection, `share_pdf`). No HTML-to-PDF by design
  (`printing`'s `convertHtml` is deprecated — generate the PDF yourself
  and pass bytes).
