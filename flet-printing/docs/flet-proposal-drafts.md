# fletへの提案・#894コメントの下書き（ユーザーが投稿する用）

## 1. flet-dev/flet#894 へのコメント（2024年の未回答質問への回答）

> @zzj0402 asked (Feb 2024): *"What's the completed solution for this?"*
>
> There wasn't one — so we built it: **flet-printing**
> https://github.com/aiseed-dev/flet-printing (PyPI: `flet-printing`)
>
> It wraps the [`printing`](https://pub.dev/packages/printing) package
> (as originally suggested in this issue) as a standard Flet extension:
>
> - `Printing` service — `print_pdf()` opens the native print dialog
>   (printer selection / copies / save-as-PDF, with cancel detection),
>   `share_pdf()` opens the share sheet
> - `PdfPreview` control — displays a PDF with built-in print/share
>   buttons, which is exactly what this issue asked for
>
> Works with `flet build` like any third-party extension. MIT licensed.
> If the Flet team is interested in adopting it as an official extension
> (so it also works with the prebuilt `flet run` client), we'd be glad
> to contribute it.

## 2. fletへの新規要望（Discussion/Issueとして投稿する用）

**Title**: Offer: flet-printing extension (native print dialog + PDF preview) — proposal for official adoption

**Body**:

> Flet currently has no printing API. The demand goes back to #894
> (Jan 2023), which suggested wrapping the `printing` Flutter package;
> it was closed as completed but no solution ever shipped, and the
> follow-up question there ("What's the completed solution for this?")
> is still unanswered.
>
> Instead of asking again, we built it first:
> **https://github.com/aiseed-dev/flet-printing** (PyPI: `flet-printing`)
>
> - `Printing` service: `print_pdf(bytes)` → native print dialog with
>   cancel detection; `share_pdf(bytes)` → share sheet / save dialog
> - `PdfPreview` control: scrollable PDF preview with built-in
>   print/share actions
> - Same structure as the official extensions (flet-audio etc.):
>   Python `ft.Service`/`ft.LayoutControl` + Dart `FletExtension`
> - Verified: `flutter analyze` clean, `flet build linux` succeeds,
>   built app runs clean; wheel ships the `flutter/` package
>
> As a third-party extension it requires `flet build`. **We propose
> adopting it as an official extension** so it is bundled with the
> prebuilt client and works with `flet run` too — printing is a basic
> capability for the document/business apps Flet is well suited for.
> We're happy to transfer or maintain it under flet-dev, whichever the
> team prefers. MIT licensed.
