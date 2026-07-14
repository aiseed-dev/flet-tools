# flet-printing の動作例

PDFプレビュー（PdfPreview）と印刷ダイアログ（Printingサービス）のデモ。

## 動かし方（2コマンド）

```bash
flet build linux --yes           # 初回のみ・数分かかる（macos/windowsも可）
./build/linux/flet-printing-example
```

- 「印刷ダイアログ」ボタン → OSの印刷ダイアログが開く
- 画面下半分 → PDFプレビュー（印刷・共有ボタン内蔵）

## なぜ `flet run` ではないのか

`flet run` はビルド済みの共通クライアントを使うため、**第三者拡張を
読み込めません**（公式拡張のみ同梱）。flet-printing のような拡張入りの
アプリは `flet build` でアプリごとコンパイルする必要があります。
出力先 `build/linux/` とバイナリ名（=pyproject.tomlのname）はFletの
規約です。
