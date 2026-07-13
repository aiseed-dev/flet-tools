# flet-printing

Native print dialog / share sheet for [Flet](https://flet.dev) apps —
wraps the Flutter [printing](https://pub.dev/packages/printing) package.

Flet has no built-in printing API. Flutter has a mature one. This
extension bridges the gap, the same way official extensions like
`flet-audio` wrap `audioplayers`.

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

A runnable example lives in `examples/flet_printing_example`
(build verified on Linux: extension registers, app launches, print
dialog opens from the button).

## Platform support

Follows the `printing` package: Android / iOS / macOS / Windows / Linux
(via CUPS) / web. See the
[printing package docs](https://pub.dev/packages/printing) for details.

## License

MIT
