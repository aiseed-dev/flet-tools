# SPDX-License-Identifier: MIT
# Copyright (c) 2026 aiseed-dev
# 雛形: https://github.com/aiseed-dev/flet-tools/tree/main/recipes/flet-windows-release

"""配布用のアプリの入口（flet build の [tool.flet.app] path の main.py として置く）。

本体の import が重い（xarray、matplotlib など）と、Windows の配布版の初回は数十秒かかる。その間、
Flet の画面の側は Python を待ちきれず、白いままになる。なので先に Flet だけで「起動しています」を
出し、本体は別のスレッドで読み込んでから画面を差し替える。開発（flet run）では本体を直接走らせる。

直す所は APP_MODULE と TITLE と文言だけ。本体のモジュールは、次を持つこと:
- App: page.render に渡す部品（@ft.component）
- configure(page)（無くてもよい）: 窓の大きさなど、page を先に整える関数
"""
import asyncio
import importlib
import logging

import flet as ft

APP_MODULE = "myapp.main"
TITLE = "My App"


async def boot(page: ft.Page) -> None:
    page.title = TITLE
    page.add(ft.Container(
        expand=True,
        alignment=ft.Alignment.CENTER,
        content=ft.Column(
            tight=True,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[ft.ProgressRing(),
                      ft.Text(f"{TITLE} を起動しています…"),
                      ft.Text("初めて開くときは 1 分ほどかかります。", size=12, color=ft.Colors.GREY)],
        ),
    ))
    try:
        app = await asyncio.to_thread(importlib.import_module, APP_MODULE)
    except Exception as exc:
        logging.getLogger(__name__).exception("%s の読み込みに失敗しました", TITLE)
        page.controls.clear()
        page.add(ft.Text(f"起動できませんでした: {type(exc).__name__}: {exc}", selectable=True))
        return
    configure = getattr(app, "configure", None)
    if configure is not None:
        configure(page)
    page.render(app.App)


ft.run(boot)
