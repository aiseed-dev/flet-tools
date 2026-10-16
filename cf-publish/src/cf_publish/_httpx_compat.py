"""httpx の版差を吸収する薄い層。**応答に直接触るのはここだけ。**

なぜ要るのか
------------
httpx 1.0 は破壊的変更を含む。1.0.dev5 で実測した差:

===========================  ==================  =========================
API                          0.28.1              1.0.dev5
===========================  ==================  =========================
``Client(timeout=...)``      あり                **削除**（下記の timeout へ）
``httpx.timeout(secs)``      無い                コンテキストマネージャ
``Response.status_code``     ``int``             ``StatusCode`` 型
``Response.content``         ``bytes``           ``HTML`` 型（``len()`` も通らない）
``Response.text``            あり                **削除**
``Response.json()``          あり                **削除**
``Response.raise_for_status``あり                **削除**
===========================  ==================  =========================

依存に ``httpx<1`` と上限を書けば当座はしのげるが、**利用者の環境を縛る**。
上限は問題の先送りで、他のパッケージと衝突する原因にもなる。だから
上限は付けず、**触る場所を 1 箇所に集めて版を検出して分岐する**。

1.0 はまだ dev で、正式版までに API が動きうる。いま dev5 に合わせて
書き込むと二度手間になるので、ここでは **0.x の呼び方を既定にし、
1.x では代替経路を通す**形にとどめる。1.0 が固まったら直すのはこの
ファイルだけで済む。

使い方
------
``resp.json()`` のように直接書かず、必ずここを通す::

    from ._httpx_compat import build_client, deadline, json_body, status, text

    client = build_client(token=..., timeout=120.0)
    with deadline(120.0):
        resp = client.request("GET", url)
    if status(resp) == 200:
        data = json_body(resp)
"""

from __future__ import annotations

import contextlib
import json as _json
from typing import Any

import httpx

# 1.0 以降は timeout が Client 引数から消え、コンテキストマネージャになった
_HAS_TIMEOUT_CM = hasattr(httpx, "timeout")


def is_v1() -> bool:
    """httpx 1.0 以降か。分岐の判定を 1 箇所に置く。"""
    return _HAS_TIMEOUT_CM


_TIMEOUT_ATTR = "_cf_publish_timeout"


def build_client(*, timeout: float, transport=None, **kw) -> httpx.Client:
    """版差を吸収して ``Client`` を作る。

    0.x は構築時に ``timeout`` を受け取る。1.x は受け取らないので落とし、
    呼ぶ側が :func:`deadline` で包む。1.x では ``Client`` が時間制限を
    覚えていないので、ここで控えておく（:func:`client_timeout` が読む）。
    """
    if transport is not None:
        kw["transport"] = transport
    if not _HAS_TIMEOUT_CM:
        kw["timeout"] = timeout
    client = httpx.Client(**kw)
    setattr(client, _TIMEOUT_ATTR, timeout)
    return client


def client_timeout(client: httpx.Client, default: float = 120.0) -> float:
    """その ``Client`` に指定された時間制限。

    1.x で :func:`deadline` に渡す値。これが無いと、アップロード用に
    300 秒で作った ``Client`` が 120 秒で切れる（0.x とふるまいが変わる）。
    """
    return getattr(client, _TIMEOUT_ATTR, default)


def deadline(seconds: float):
    """時間制限。0.x では Client 側で設定済みなので何もしない。"""
    if _HAS_TIMEOUT_CM:
        return httpx.timeout(seconds)
    return contextlib.nullcontext()


def status(resp: httpx.Response) -> int:
    """状態コードを ``int`` で返す。1.x は ``StatusCode`` 型を返すため。"""
    return int(resp.status_code)


def raw(resp: httpx.Response) -> bytes:
    """本文を ``bytes`` で返す。1.x の ``content`` は bytes ではない。"""
    body = resp.content
    if isinstance(body, bytes):
        return body
    if isinstance(body, (bytearray, memoryview)):
        return bytes(body)
    # 1.x: ``content`` は解釈済みの包み（JSON / HTML など）で bytes ではない。
    # 生の本文は ``body`` にある（1.0.dev5 で実測）
    got = getattr(resp, "body", None)
    if isinstance(got, (bytes, bytearray)):
        return bytes(got)
    # さらに別の形なら read() を試す
    reader = getattr(resp, "read", None)
    if callable(reader):
        got = reader()
        if isinstance(got, (bytes, bytearray)):
            return bytes(got)
    # ここに来たら httpx がまた変わっている。str() で包みの見た目を本文の
    # ふりをさせると、その先で「壊れた JSON」「壊れた XML」として現れる。
    from .pages import PagesError  # 循環参照を避けるためここで読む

    raise PagesError(
        f"cannot read the response body from httpx {httpx.__version__}: "
        f"content is {type(body).__name__}. Please report this with the "
        f"httpx version — cf-publish needs an update for it.")


def text(resp: httpx.Response) -> str:
    """本文を ``str`` で返す。``Response.text`` は 1.x に無い。"""
    got = getattr(resp, "text", None)
    if isinstance(got, str):
        return got
    return raw(resp).decode("utf-8", errors="replace")


def json_body(resp: httpx.Response) -> Any:
    """本文を JSON として読む。``Response.json()`` は 1.x に無い。

    解析できないときは :class:`ValueError` を投げる（呼ぶ側が
    「JSON でない応答」として扱えるよう、0.x と同じ振る舞いにする）。
    """
    meth = getattr(resp, "json", None)
    if callable(meth):
        return meth()
    return _json.loads(raw(resp))


def request_url(resp: httpx.Response) -> str:
    """要求 URL。誤りの報告に使う。無い版でも落ちないようにする。"""
    req = getattr(resp, "request", None)
    return str(getattr(req, "url", "")) if req is not None else ""
