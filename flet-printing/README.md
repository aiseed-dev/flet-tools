# flet-printing

Native print dialog / share sheet for [Flet](https://flet.dev) apps —
wraps the Flutter [printing](https://pub.dev/packages/printing) package.

Flet has no built-in printing API. Flutter has a mature one. This
extension bridges the gap, the same way official extensions like
`flet-audio` wrap `audioplayers`.

The demand is documented:
[flet-dev/flet#894](https://github.com/flet-dev/flet/issues/894)
(Jan 2023) asked for exactly this — PDF printing via the `printing`
package — was closed as "completed" without a shipped solution, and the
follow-up question *"What's the completed solution for this?"* (Feb
2024) was never answered. This package is that answer.

日本語補足: Fletには印刷APIがありません（0.85時点・全API確認済み）。
Flutterの`printing`パッケージ（ネイティブ印刷ダイアログ・共有シート）を
Flet拡張として包んだものです。ワープロ的なアプリの「ファイル→印刷…」を
Fletで実装できます。

## Usage

```python
import flet as ft
from flet_printing import Printing

def main(page: ft.Page):
    printing = Printing()
    page.services.append(printing)

    async def print_click(e):
        pdf = open("document.pdf", "rb").read()
        sent = await printing.print_pdf(pdf, name="document")
        # sent=True: 印刷された / False: ダイアログでキャンセル

    page.add(ft.FilledButton("印刷…", on_click=print_click))

ft.run(main)
```

API:

- `await printing.print_pdf(pdf, name="document")` — open the platform
  print dialog (printer selection / copies / duplex / save-as-PDF) for
  the given PDF bytes. Returns `False` if the user cancelled.
- `await printing.share_pdf(pdf, filename="document.pdf")` — open the
  platform share sheet (mobile) / save dialog (desktop).

### PdfPreview — display a PDF with print/share built in

```python
from flet_printing import PdfPreview

page.add(PdfPreview(src=pdf_bytes, pdf_file_name="document.pdf",
                    expand=True))
```

Renders the PDF pages (scrollable) with an action bar: print and share
buttons work out of the box. Properties: `src` (bytes or base64),
`allow_printing`, `allow_sharing`, `use_actions`, `pdf_file_name`,
`on_printed`/`on_shared` events. `can_change_page_format` /
`can_change_orientation` are off by default (the PDF you pass is
already laid out).

There is deliberately no HTML-to-PDF here: `printing`'s `convertHtml` is
deprecated. Generate the PDF yourself (e.g. headless Chrome for exact
CJK typesetting) and pass the bytes to `print_pdf`.

## Installation

Like every third-party Flet extension, this works with apps compiled via
`flet build` (the prebuilt `flet run` client only bundles official
extensions).

Add to your app's `pyproject.toml`:

```toml
dependencies = [
  "flet-printing",
  "flet>=0.85.3",
]
```

then `flet build linux` (or `windows` / `macos` / `apk` / `ipa`).
The Usage snippets above are complete runnable apps — paste one into
your app's `main.py` to try it (build verified on Linux: extension
registers, app launches, print dialog opens).

## Platform support

Follows the `printing` package: Android / iOS / macOS / Windows / Linux
(via CUPS) / web. See the
[printing package docs](https://pub.dev/packages/printing) for details.

## License

MIT
