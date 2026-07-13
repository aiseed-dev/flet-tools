"""flet-printing の例: PDFプレビュー表示と印刷ダイアログ/共有シート。

実行: この examples/flet_printing_example で `flet build linux`（等）して
ビルド済みアプリとして起動する（サードパーティ拡張は flet build が必要）。
"""
import flet as ft

from flet_printing import PdfPreview, Printing

# 依存を増やさないための最小PDF（Hello worldの1頁・手書きPDF）
MINIMAL_PDF = b"""%PDF-1.4
1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj
2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj
3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842]
  /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >> endobj
4 0 obj << /Length 62 >> stream
BT /F1 24 Tf 100 700 Td (Hello from flet-printing!) Tj ET
endstream endobj
5 0 obj << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> endobj
trailer << /Root 1 0 R >>
"""


def main(page: ft.Page):
    printing = Printing()
    page.services.append(printing)
    status = ft.Text("")

    async def print_click(e):
        ok = await printing.print_pdf(MINIMAL_PDF, name="flet-printing example")
        status.value = "印刷しました" if ok else "キャンセルされました"
        page.update()

    page.add(
        ft.Row([
            ft.FilledButton("印刷ダイアログ（Printingサービス）",
                            on_click=print_click),
            status,
        ]),
        # PdfPreview: PDF表示＋印刷/共有ボタン内蔵（flet-dev/flet#894 の
        # 「PDFを表示して印刷・保存できるウィジェット」への回答）
        PdfPreview(src=MINIMAL_PDF, pdf_file_name="example.pdf", expand=True),
    )


ft.run(main)
