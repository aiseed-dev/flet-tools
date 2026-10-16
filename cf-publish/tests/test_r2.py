"""R2 sync tests: SigV4 pinned to the AWS documentation vector, sync logic
against a mocked S3 API (httpx.MockTransport)."""

from __future__ import annotations

import base64
import hashlib

import httpx
import pytest

import cf_publish.pages as pages
from cf_publish.pages import PagesError
from cf_publish.r2 import sign_v4, sync


def test_sigv4_aws_documentation_vector():
    """The canonical S3 GET Object example from the AWS SigV4 docs
    (examplebucket/test.txt, 20130524). If this breaks, every request
    signature is wrong."""
    empty = hashlib.sha256(b"").hexdigest()
    out = sign_v4(
        "GET", "examplebucket.s3.amazonaws.com", "/test.txt", {},
        {"range": "bytes=0-9"}, empty,
        "AKIAIOSFODNN7EXAMPLE", "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
        region="us-east-1", amz_date="20130524T000000Z")
    assert out["Authorization"].endswith(
        "Signature=f0e8bdb87c964420e857bd35b5d6ed310bd44f0170aba48dd91039c6036bdb41")
    assert "SignedHeaders=host;range;x-amz-content-sha256;x-amz-date" in out["Authorization"]


ACCOUNT = "acc123"
LIST_XML = """<?xml version="1.0" encoding="UTF-8"?>
<ListBucketResult xmlns="http://s3.amazonaws.com/doc/2006-03-01/">
  <Name>data</Name>{contents}
</ListBucketResult>"""


class FakeR2:
    """R2 として最低限正直なサーバ。PUT には本物と同じく ETag を返す。

    ``lies`` に鍵を入れると、**2 回目以降の一覧**で別の ETag を返す
    ——「保存したと言っているが、読み直すと中身が違う」サーバになる。
    配布でいちばん怖い形を再現するため。
    """

    NO_ETAG = "(none)"  # put_etag に渡すと ETag を返さないサーバになる

    def __init__(self, objects: "dict[str, bytes]", lies: "set[str]" = frozenset(),
                 put_etag: "str | None" = None):
        self.objects = dict(objects)
        self.lies = set(lies)
        self.put_etag = put_etag  # None なら本物どおり中身の MD5 を返す
        self.listings = 0
        self.puts: list[str] = []
        self.deletes: list[str] = []

    def transport(self):
        return httpx.MockTransport(self.handle)

    def handle(self, request: httpx.Request) -> httpx.Response:
        assert request.headers.get("Authorization", "").startswith("AWS4-HMAC-SHA256")
        path = request.url.path
        if request.method == "GET" and path == "/data":
            lying = self.listings > 0  # 最初の一覧は正直（差分判定はそれを見る）
            self.listings += 1
            contents = "".join(
                f"<Contents><Key>{k}</Key><ETag>&quot;"
                f"{'0' * 32 if lying and k in self.lies else hashlib.md5(v).hexdigest()}"
                f"&quot;</ETag></Contents>"
                for k, v in sorted(self.objects.items()))
            return httpx.Response(200, text=LIST_XML.format(contents=contents))
        key = path.split("/", 2)[2]
        if request.method == "PUT":
            # 本物の R2 は Content-MD5 を検算して、合わなければ 400 を返す
            sent = request.headers.get("content-md5")
            assert sent, "Content-MD5 が付いていない"
            if base64.b64decode(sent) != hashlib.md5(request.content).digest():
                return httpx.Response(400, text="<Error>BadDigest</Error>")
            self.objects[key] = request.content
            self.puts.append(key)
            if self.put_etag == self.NO_ETAG:
                return httpx.Response(200)
            etag = self.put_etag or hashlib.md5(request.content).hexdigest()
            return httpx.Response(200, headers={"ETag": f'"{etag}"'})
        if request.method == "DELETE":
            self.objects.pop(key, None)
            self.deletes.append(key)
            return httpx.Response(204)
        raise AssertionError(f"unexpected {request.method} {path}")


@pytest.fixture(autouse=True)
def creds(monkeypatch):
    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", ACCOUNT)
    monkeypatch.setenv("R2_ACCESS_KEY_ID", "rk")
    monkeypatch.setenv("R2_SECRET_ACCESS_KEY", "rs")
    monkeypatch.setattr(pages, "RETRY_DELAYS", (0.0,))


@pytest.fixture
def tree(tmp_path):
    (tmp_path / "a.txt").write_bytes(b"alpha")
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "b.bin").write_bytes(b"beta")
    return tmp_path


def test_sync_uploads_new_and_changed_skips_same(tree):
    r2 = FakeR2({"pre/a.txt": b"alpha",        # 一致 → skip
                 "pre/sub/b.bin": b"STALE",    # 不一致 → 再アップロード
                 "pre/gone.txt": b"x"})        # ローカルに無い → delete 指定時のみ
    res = sync(tree, "data/pre", transport=r2.transport())
    assert (res.files, res.uploaded, res.skipped, res.deleted) == (2, 1, 1, 0)
    assert r2.puts == ["pre/sub/b.bin"]
    assert "pre/gone.txt" in r2.objects  # --delete なしでは残る


def test_sync_delete_removes_remote_only(tree):
    r2 = FakeR2({"pre/gone.txt": b"x"})
    res = sync(tree, "data/pre", delete=True, transport=r2.transport())
    assert res.deleted == 1 and r2.deletes == ["pre/gone.txt"]
    assert sorted(r2.puts) == ["pre/a.txt", "pre/sub/b.bin"]


def test_sync_dry_run_touches_nothing(tree):
    r2 = FakeR2({"pre/gone.txt": b"x"})
    msgs: list[str] = []
    res = sync(tree, "data/pre", delete=True, dry_run=True,
               transport=r2.transport(), on_progress=msgs.append)
    assert res.dry_run and res.uploaded == 2 and res.deleted == 1
    assert r2.puts == [] and r2.deletes == []
    assert any("would upload" in m for m in msgs) and any("would delete" in m for m in msgs)


def test_sync_no_prefix(tree):
    r2 = FakeR2({})
    res = sync(tree, "data", transport=r2.transport())
    assert sorted(r2.puts) == ["a.txt", "sub/b.bin"]
    assert res.prefix == ""


def test_upload_sends_content_md5_and_checks_the_answered_etag(tree):
    """送りは Content-MD5 でサーバに検算させ、返る ETag もこちらで照合する。"""
    r2 = FakeR2({})
    seen: list[str] = []

    def handle(request):
        if request.method == "PUT":
            seen.append(request.headers.get("content-md5", ""))
            # 署名にも含まれていること(後から足した頭は署名が壊れる)
            assert "content-md5" in request.headers["Authorization"]
        return r2.handle(request)

    sync(tree, "data", transport=httpx.MockTransport(handle))
    assert len(seen) == 2 and all(len(base64.b64decode(s)) == 16 for s in seen)


def test_server_storing_different_bytes_is_caught_at_the_put(tree):
    """「上げたことになっているが中身が違う」— その場で止める。"""
    r2 = FakeR2({}, put_etag="f" * 32)
    with pytest.raises(PagesError, match="stored different bytes"):
        sync(tree, "data", transport=r2.transport())


def test_put_without_an_etag_is_not_treated_as_success(tree):
    r2 = FakeR2({}, put_etag=FakeR2.NO_ETAG)
    with pytest.raises(PagesError, match="no ETag"):
        sync(tree, "data", transport=r2.transport())


def test_verify_reads_the_bucket_back(tree):
    r2 = FakeR2({})
    msgs: list[str] = []
    res = sync(tree, "data/pre", verify=True, transport=r2.transport(),
               on_progress=msgs.append)
    assert res.verified == 2
    assert any("verified 2 objects" in m for m in msgs)


def test_verify_catches_a_bucket_that_disagrees_afterwards(tree):
    """PUT は正しい ETag を返すのに、読み直すと中身が違うサーバ。"""
    r2 = FakeR2({}, lies={"pre/sub/b.bin"})
    with pytest.raises(PagesError, match=r"verification failed for 1 of 2"):
        sync(tree, "data/pre", verify=True, transport=r2.transport())


def test_verify_covers_unchanged_files_too(tree):
    """一致として飛ばした物も照合する(飛ばした判断そのものが古い場合がある)。"""
    r2 = FakeR2({"pre/a.txt": b"alpha", "pre/sub/b.bin": b"beta"},
                lies={"pre/a.txt"})
    with pytest.raises(PagesError, match="pre/a.txt"):
        sync(tree, "data/pre", verify=True, transport=r2.transport())
    assert r2.puts == []  # 送る物は無かったが、照合はした


def test_verify_notices_a_delete_that_did_not_happen(tree):
    r2 = FakeR2({"pre/gone.txt": b"x"})
    r2.delete_object = None  # 使わない（下で handle を差し替える）

    def handle(request):
        if request.method == "DELETE":
            return httpx.Response(204)  # 消したふりをするサーバ
        return r2.handle(request)

    with pytest.raises(PagesError, match="still in the bucket"):
        sync(tree, "data/pre", delete=True, verify=True,
             transport=httpx.MockTransport(handle))


def test_verify_does_nothing_on_a_dry_run(tree):
    r2 = FakeR2({})
    res = sync(tree, "data", verify=True, dry_run=True, transport=r2.transport())
    assert res.dry_run and res.verified == 0 and r2.puts == []


def test_missing_r2_credentials(tree, monkeypatch, tmp_path):
    monkeypatch.delenv("R2_ACCESS_KEY_ID")
    monkeypatch.setattr(pages, "ENV_FILE", tmp_path / "absent.env")
    with pytest.raises(PagesError, match="R2_ACCESS_KEY_ID"):
        sync(tree, "data")


def _server_side_verify(request: httpx.Request) -> None:
    """受信したバイト列から、サーバがやるのと同じ手順で署名を再計算して照合。"""
    from urllib.parse import parse_qsl
    raw = request.url.raw_path.decode()
    path, _, qs = raw.partition("?")
    q = dict(parse_qsl(qs, keep_blank_values=True))
    extra = {}
    if request.method == "PUT":
        for name in ("content-type", "content-md5"):
            if name in request.headers:
                extra[name] = request.headers[name]
    payload = hashlib.sha256(request.content).hexdigest()
    expected = sign_v4(request.method, request.url.host, path, q, extra,
                       payload, "rk", "rs",
                       amz_date=request.headers["x-amz-date"])
    assert request.headers["Authorization"] == expected["Authorization"], raw


def test_query_and_path_bytes_match_signature(tree):
    """送信バイト列が署名した正規化形と一致する（空白入りprefixの回帰）。

    以前は params= 経由で httpx が再符号化しており、空白が + になって
    署名（%20）とずれ、RFC3986どおりに検証するサーバでは403になり得た。
    """
    calls: list[str] = []

    def handle(request: httpx.Request) -> httpx.Response:
        _server_side_verify(request)
        calls.append(request.url.raw_path.decode())
        if request.method == "GET":
            return httpx.Response(200, text=LIST_XML.format(contents=""))
        etag = hashlib.md5(request.content).hexdigest()
        return httpx.Response(200, headers={"ETag": f'"{etag}"'})

    sync(tree, "data/a b", transport=httpx.MockTransport(handle))
    listing = next(c for c in calls if "?" in c)
    assert "prefix=a%20b%2F" in listing
    assert "+" not in listing.split("?", 1)[1]
    # PUT のパスも空白が %20 のまま(署名と同一バイト)で送られている
    assert any(c.startswith("/data/a%20b/") for c in calls if "?" not in c)
