"""Printing service control for Flet — native print dialog via the Flutter
``printing`` package.

Flet has no built-in printing API (verified against Flet 0.85: nothing
print/PDF-related is exposed), while Flutter has a mature ``printing``
package (native print dialog, share sheet, PDF rasterization). This
extension bridges the two, the same way official extensions like
``flet-audio`` wrap ``audioplayers``.

Usage::

    import flet as ft
    from flet_printing import Printing

    def main(page: ft.Page):
        printing = Printing()
        page.services.append(printing)

        async def print_click(e):
            pdf = open("document.pdf", "rb").read()
            await printing.print_pdf(pdf, name="document")

        page.add(ft.FilledButton("印刷…", on_click=print_click))

    ft.run(main)

Note:
    Like every third-party Flet extension, this works with apps compiled
    via ``flet build`` (the prebuilt ``flet run`` client only bundles
    official extensions).
"""

from typing import Optional, Union

import flet as ft

__all__ = ["Printing"]


@ft.control("Printing")
class Printing(ft.Service):
    """Native printing — print dialog and share sheet for PDF documents.

    A non-visual service control. Add it to ``page.services`` and call its
    async methods. Wraps the Flutter `printing
    <https://pub.dev/packages/printing>`_ package.
    """

    async def print_pdf(
        self,
        pdf: Union[bytes, str],
        name: str = "document",
        timeout: Optional[float] = None,
    ) -> bool:
        """Open the platform print dialog for a PDF document.

        The dialog offers printer selection, copies, duplex, page ranges
        and (on most platforms) "save as PDF" — everything a word
        processor's File→Print is expected to provide.

        Args:
            pdf: PDF document bytes (or a base64-encoded string).
            name: Print job name shown in the printer queue.
            timeout: Seconds to wait for the dialog to be dismissed.
                ``None`` waits indefinitely (the method returns after the
                user prints or cancels).

        Returns:
            ``True`` if the document was sent to the printer,
            ``False`` if the user cancelled the dialog.
        """
        return await self._invoke_method(
            "print_pdf",
            arguments={"pdf": pdf, "name": name},
            timeout=timeout,
        )

    async def share_pdf(
        self,
        pdf: Union[bytes, str],
        filename: str = "document.pdf",
        timeout: Optional[float] = None,
    ) -> bool:
        """Open the platform share sheet for a PDF document.

        On desktop this typically shows a save dialog; on mobile the
        share sheet (mail, files, AirDrop, …).

        Args:
            pdf: PDF document bytes (or a base64-encoded string).
            filename: Suggested file name.
            timeout: Seconds to wait. ``None`` waits indefinitely.

        Returns:
            ``True`` on success.
        """
        return await self._invoke_method(
            "share_pdf",
            arguments={"pdf": pdf, "filename": filename},
            timeout=timeout,
        )

# print_html は載せない: printingパッケージのconvertHtmlは非推奨
# (deprecated)になっており、推奨経路は「PDFは自前で生成してprint_pdfへ
# 渡す」。HTMLの組版が要るならヘッドレスChrome等で確定的なPDFを作る方が
# 忠実度も高い(このパッケージの出自であるAISeed工房もその方式)。
