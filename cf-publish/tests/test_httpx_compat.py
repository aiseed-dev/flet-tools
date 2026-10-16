"""httpx の版差を吸収する層の試験。

**実物の httpx に対して確かめる。** MockTransport は 1.0 で削除されており、
モックで固めると「モックの中でだけ正しい」ものになる。ここでは偽の応答
オブジェクトを作って、版ごとの形の違いを再現する。
"""
import json

import pytest

from cf_publish import _httpx_compat as c


class _V0Response:
    """httpx 0.x の応答。content は bytes、text と json() を持つ。"""
    status_code = 200

    def __init__(self, body: bytes):
        self.content = body
        self.text = body.decode()

    def json(self):
        return json.loads(self.content)


class _JSONWrapper:
    """1.x の ``content``。解釈済みの包みで bytes ではない（len も通らない）。"""
    def __init__(self, data):
        self._data = data

    def __repr__(self):
        return f"<JSON {self._data}>"


class _V1Response:
    """httpx 1.x の応答。content は包み、生の本文は body、text/json は無い。"""
    def __init__(self, body: bytes):
        self.body = body
        self.content = _JSONWrapper(json.loads(body))
        self.status_code = 200          # 実物は StatusCode 型だが int 互換


BODY = b'{"success":true,"result":{"id":"abc"}}'


@pytest.mark.parametrize("resp", [_V0Response(BODY), _V1Response(BODY)],
                         ids=["httpx-0.x", "httpx-1.x"])
def test_reads_the_same_body_on_both_versions(resp):
    """どちらの形でも bytes / str / dict が同じに取れること。

    ここが崩れると、応答を読む全ての場所が版によって違う振る舞いをする。
    """
    assert c.raw(resp) == BODY
    assert c.text(resp) == BODY.decode()
    assert c.json_body(resp) == {"success": True, "result": {"id": "abc"}}
    assert c.status(resp) == 200
    assert isinstance(c.status(resp), int)


def test_unknown_body_shape_is_reported_not_guessed():
    """未知の形は**推測せずに落とす**。

    str() で包みの見た目を本文のふりをさせると、その先で「壊れた JSON」
    として現れ、原因が追えなくなる。
    """
    class _Alien:
        status_code = 200
        content = object()

    from cf_publish.pages import PagesError
    with pytest.raises(PagesError, match="cannot read the response body"):
        c.raw(_Alien())


def test_client_timeout_is_remembered():
    """1.x は Client が時間制限を覚えないので、こちらで控える。

    これが無いと、アップロード用に 300 秒で作った Client が
    deadline(120) で切られる（0.x とふるまいが変わる）。
    """
    client = c.build_client(timeout=300.0)
    assert c.client_timeout(client) == 300.0
    client.close()
