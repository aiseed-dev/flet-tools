"""PdfPreview visual control — display a PDF with built-in print/share
actions (wraps `printing`'s PdfPreview widget).

Together with :class:`~flet_printing.Printing` this answers
`flet-dev/flet#894 <https://github.com/flet-dev/flet/issues/894>`_ in
full: the original 2023 request asked to *"display a PDF in a widget
that allows printing or saving it"*.
"""

from typing import Optional, Union

import flet as ft

__all__ = ["PdfPreview"]


@ft.control("PdfPreview")
class PdfPreview(ft.LayoutControl):
    """Display a PDF document with print / share actions.

    Renders the pages of a PDF (scrollable) and, by default, shows an
    action bar with print and share buttons — no extra wiring needed::

        import flet as ft
        from flet_printing import PdfPreview

        def main(page: ft.Page):
            pdf = open("document.pdf", "rb").read()
            page.add(PdfPreview(src=pdf, expand=True))

        ft.run(main)
    """

    src: Optional[Union[str, bytes]] = None
    """
    The PDF document: raw ``bytes`` or a base64-encoded string.
    """

    allow_printing: bool = True
    """
    Show the print action button.
    """

    allow_sharing: bool = True
    """
    Show the share action button (share sheet on mobile,
    save dialog on desktop).
    """

    use_actions: bool = True
    """
    Show the action bar at all. Set to ``False`` for a bare preview.
    """

    can_change_page_format: bool = False
    """
    Let the viewer switch page formats. Off by default: the PDF passed
    in ``src`` is already laid out, so reflowing is usually meaningless.
    """

    can_change_orientation: bool = False
    """
    Let the viewer switch page orientation. Off by default, same
    reasoning as ``can_change_page_format``.
    """

    pdf_file_name: Optional[str] = None
    """
    Suggested file name when the viewer shares/saves the document.
    """

    on_printed: Optional[ft.ControlEventHandler["PdfPreview"]] = None
    """
    Fires after the document was sent to the printer.
    """

    on_shared: Optional[ft.ControlEventHandler["PdfPreview"]] = None
    """
    Fires after the document was shared/saved.
    """
