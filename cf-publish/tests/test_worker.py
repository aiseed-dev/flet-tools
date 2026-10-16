"""Worker deploy tests: wrangler.toml reading (both parsers), the multipart
upload the Cloudflare API demands, bindings, cron and bucket creation —
against a mocked API (httpx.MockTransport)."""

from __future__ import annotations

import json

import httpx
import pytest

import cf_publish.pages as pages
from cf_publish.pages import PagesError
from cf_publish.worker import (config_defaults, deploy_worker, parse_pair,
                               parse_toml_subset, read_config)

ACCOUNT = "acc123"

WRANGLER = """\
# アメダス 10 分値の収集 Worker
name = "amedas-collector"
main = "worker.js"
compatibility_date = "2026-08-27"

[triggers]
crons = ["*/10 * * * *"]   # 10 分ごと

[[r2_buckets]]
binding = "AMEDAS"
bucket_name = "weather-amedas"

[observability]
enabled = true
"""


class FakeAPI:
    """The Workers/R2 endpoints, enough to see what the client sends."""

    def __init__(self, buckets=()):
        self.buckets = set(buckets)
        self.uploads: list[tuple[str, dict, dict]] = []  # name, metadata, modules
        self.crons: dict[str, list] = {}
        self.created: list[str] = []
        self.subdomain_calls: list[bool] = []

    def transport(self):
        return httpx.MockTransport(self.handle)

    def handle(self, request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "Bearer tok"
        path = request.url.path.replace(f"/client/v4/accounts/{ACCOUNT}", "")
        ok = {"success": True, "errors": [], "result": {}}

        if request.method == "GET" and path.startswith("/r2/buckets/"):
            name = path.rsplit("/", 1)[1]
            return httpx.Response(200 if name in self.buckets else 404, json=ok)
        if request.method == "POST" and path == "/r2/buckets":
            name = json.loads(request.content)["name"]
            self.buckets.add(name)
            self.created.append(name)
            return httpx.Response(200, json=ok)
        if request.method == "PUT" and path.startswith("/workers/scripts/"):
            name = path[len("/workers/scripts/"):]
            if name.endswith("/schedules"):
                self.crons[name[:-len("/schedules")]] = json.loads(request.content)
                return httpx.Response(200, json=ok)
            metadata, modules = _read_multipart(request)
            self.uploads.append((name, metadata, modules))
            return httpx.Response(200, json=ok)
        if request.method == "POST" and path.endswith("/subdomain"):
            self.subdomain_calls.append(json.loads(request.content)["enabled"])
            return httpx.Response(200, json=ok)
        if request.method == "GET" and path == "/workers/subdomain":
            return httpx.Response(200, json={"success": True, "errors": [],
                                             "result": {"subdomain": "acme"}})
        raise AssertionError(f"unexpected {request.method} {path}")


def _read_multipart(request: httpx.Request):
    """Split the upload body into the metadata dict and {part name: (body, type)}.

    Deliberately parsed from the raw bytes: the Cloudflare API rejects the
    upload unless the script part is a *file* part whose name equals
    main_module and whose type is application/javascript+module, and that is
    exactly the sort of thing a mock that trusts httpx would never catch.
    """
    ctype = request.headers["content-type"]
    assert ctype.startswith("multipart/form-data; boundary=")
    boundary = ctype.split("boundary=", 1)[1].strip('"')
    parts = request.content.split(b"--" + boundary.encode())
    metadata = None
    modules: dict[str, tuple[bytes, str]] = {}
    for part in parts:
        part = part.strip(b"\r\n")
        if not part or part == b"--":
            continue
        head, _, body = part.partition(b"\r\n\r\n")
        headers = head.decode()
        name = headers.split('name="', 1)[1].split('"', 1)[0]
        part_type = headers.split("Content-Type: ", 1)[1].split("\r\n")[0]
        if name == "metadata":
            metadata = json.loads(body)
        else:
            assert f'filename="{name}"' in headers, f"{name} must be a file part"
            modules[name] = (body, part_type)
    assert metadata is not None, "no metadata part"
    return metadata, modules


@pytest.fixture(autouse=True)
def creds(monkeypatch):
    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", ACCOUNT)
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "tok")
    monkeypatch.setattr(pages, "RETRY_DELAYS", (0.0,))


@pytest.fixture
def worker_dir(tmp_path):
    (tmp_path / "wrangler.toml").write_text(WRANGLER, encoding="utf-8")
    (tmp_path / "worker.js").write_text("export default { async fetch() {} }")
    (tmp_path / "lib.js").write_text("export const x = 1")
    (tmp_path / "README.md").write_text("not a module")
    return tmp_path


# ---------------------------------------------------------------- config

def test_toml_subset_reads_wrangler():
    data = parse_toml_subset(WRANGLER)
    assert data["name"] == "amedas-collector"
    assert data["triggers"]["crons"] == ["*/10 * * * *"]      # 行末コメント付き
    assert data["r2_buckets"] == [{"binding": "AMEDAS",
                                   "bucket_name": "weather-amedas"}]
    assert data["observability"] == {"enabled": True}


def test_toml_subset_matches_tomllib():
    tomllib = pytest.importorskip("tomllib")
    assert parse_toml_subset(WRANGLER) == tomllib.loads(WRANGLER)


def test_toml_subset_refuses_what_it_cannot_read():
    with pytest.raises(PagesError, match="inline tables"):
        parse_toml_subset('name = "x"\nkv = { id = "1" }\n')


def test_config_read_falls_back_when_tomllib_is_missing(worker_dir, monkeypatch):
    """3.9/3.10 は tomllib が無い。fallback でも同じ設定が読めること。"""
    import builtins
    real_import = builtins.__import__

    def no_toml(name, *a, **kw):
        if name in ("tomllib", "tomli"):
            raise ModuleNotFoundError(name)
        return real_import(name, *a, **kw)

    monkeypatch.setattr(builtins, "__import__", no_toml)
    assert config_defaults(read_config(worker_dir / "wrangler.toml"))["name"] \
        == "amedas-collector"


def test_unsupported_bindings_stop_the_deploy(worker_dir):
    """送れないバインディングを黙って落とすと、実行時に別の場所で壊れる。"""
    (worker_dir / "wrangler.toml").write_text(
        WRANGLER + '\n[[kv_namespaces]]\nbinding = "CACHE"\nid = "abc"\n',
        encoding="utf-8")
    with pytest.raises(PagesError, match="kv_namespaces"):
        deploy_worker(worker_dir)


def test_incomplete_r2_binding_is_an_error():
    with pytest.raises(PagesError, match=r"\[\[r2_buckets\]\]"):
        config_defaults({"r2_buckets": [{"binding": "AMEDAS"}]})


def test_parse_pair_rejects_missing_equals():
    assert parse_pair("AMEDAS=weather-amedas", "r2") == ("AMEDAS", "weather-amedas")
    with pytest.raises(PagesError, match="NAME=VALUE"):
        parse_pair("AMEDAS", "r2")


# ---------------------------------------------------------------- deploy

def test_deploy_from_wrangler_toml(worker_dir):
    api = FakeAPI()
    res = deploy_worker(worker_dir, transport=api.transport())

    name, metadata, modules = api.uploads[0]
    assert name == "amedas-collector"
    assert metadata["main_module"] == "worker.js"
    assert metadata["compatibility_date"] == "2026-08-27"
    assert metadata["bindings"] == [{"type": "r2_bucket", "name": "AMEDAS",
                                     "bucket_name": "weather-amedas"}]
    # 再デプロイでシークレットが消えないための指定
    assert metadata["keep_bindings"] == ["secret_text"]
    # モジュールだけが上がる(README.md は入らない)。型は API の要求どおり
    assert set(modules) == {"worker.js", "lib.js"}
    assert modules["worker.js"][1] == "application/javascript+module"
    assert api.crons["amedas-collector"] == [{"cron": "*/10 * * * *"}]
    assert api.created == ["weather-amedas"]  # 無かったので作った
    assert (res.name, res.modules, res.bindings) == ("amedas-collector", 2, 1)
    assert res.crons == ["*/10 * * * *"] and res.url == ""


def test_existing_bucket_is_not_recreated(worker_dir):
    api = FakeAPI(buckets={"weather-amedas"})
    res = deploy_worker(worker_dir, transport=api.transport())
    assert api.created == [] and res.buckets_created == []


def test_no_create_buckets_skips_the_lookup(worker_dir):
    api = FakeAPI()
    deploy_worker(worker_dir, create_buckets=False, transport=api.transport())
    assert api.created == []


def test_flags_win_over_the_file_and_merge_bindings(worker_dir):
    api = FakeAPI()
    deploy_worker(worker_dir, name="other", r2=[("MIRROR", "b2")],
                  variables=[("BASE", "https://x")], crons=["0 * * * *"],
                  compatibility_date="2026-01-01", transport=api.transport())
    name, metadata, _ = api.uploads[0]
    assert name == "other" and metadata["compatibility_date"] == "2026-01-01"
    kinds = {(b["name"], b["type"]) for b in metadata["bindings"]}
    assert kinds == {("AMEDAS", "r2_bucket"), ("MIRROR", "r2_bucket"),
                     ("BASE", "plain_text")}
    assert api.crons["other"] == [{"cron": "0 * * * *"}]  # 置き換え、追加ではない


def test_secret_comes_from_the_environment_and_is_not_printed(worker_dir, monkeypatch):
    monkeypatch.setenv("RUN_TOKEN", "s3cret")
    api = FakeAPI()
    msgs: list[str] = []
    deploy_worker(worker_dir, secrets=["RUN_TOKEN"], transport=api.transport(),
                  on_progress=msgs.append)
    _, metadata, _ = api.uploads[0]
    assert {"type": "secret_text", "name": "RUN_TOKEN",
            "text": "s3cret"} in metadata["bindings"]
    assert not any("s3cret" in m for m in msgs)


def test_missing_secret_stops_before_uploading(worker_dir, monkeypatch, tmp_path):
    monkeypatch.delenv("RUN_TOKEN", raising=False)
    monkeypatch.setattr(pages, "ENV_FILE", tmp_path / "absent.env")
    api = FakeAPI()
    with pytest.raises(PagesError, match="RUN_TOKEN"):
        deploy_worker(worker_dir, secrets=["RUN_TOKEN"], transport=api.transport())
    assert api.uploads == []


def test_workers_dev_is_left_alone_by_default(worker_dir):
    api = FakeAPI()
    deploy_worker(worker_dir, transport=api.transport())
    assert api.subdomain_calls == []


def test_workers_dev_enabled_returns_the_url(worker_dir):
    api = FakeAPI()
    res = deploy_worker(worker_dir, workers_dev=True, transport=api.transport())
    assert api.subdomain_calls == [True]
    assert res.url == "https://amedas-collector.acme.workers.dev"


def test_dry_run_touches_nothing(worker_dir):
    api = FakeAPI()
    msgs: list[str] = []
    res = deploy_worker(worker_dir, dry_run=True, transport=api.transport(),
                        on_progress=msgs.append)
    assert res.dry_run and res.modules == 2
    assert api.uploads == [] and api.created == [] and api.crons == {}
    assert any("would upload worker.js" in m for m in msgs)


def test_no_name_anywhere_is_an_error(tmp_path):
    (tmp_path / "worker.js").write_text("x")
    with pytest.raises(PagesError, match="no script name"):
        deploy_worker(tmp_path)


def test_ambiguous_entry_module_is_an_error(tmp_path):
    (tmp_path / "a.js").write_text("x")
    (tmp_path / "b.js").write_text("y")
    with pytest.raises(PagesError, match="which module is the entry point"):
        deploy_worker(tmp_path, name="w")


def test_service_worker_format_is_refused(tmp_path):
    """旧形式は上がってしまい、実行時に黙って何もしない。上げる前に止める。"""
    (tmp_path / "worker.js").write_text(
        "addEventListener('fetch', event => event.respondWith(new Response('x')))")
    with pytest.raises(PagesError, match="service-worker format"):
        deploy_worker(tmp_path, name="w")


def test_missing_entry_module_is_an_error(tmp_path):
    (tmp_path / "a.js").write_text("x")
    with pytest.raises(PagesError, match="entry module not found"):
        deploy_worker(tmp_path, name="w", main="worker.js")


def test_hidden_check_looks_below_the_directory_only(worker_dir):
    """親に隠しディレクトリがあっても(~/.config/... の下など)モジュールは消えない。"""
    hidden_parent = worker_dir / ".stash" / "amedas"
    hidden_parent.mkdir(parents=True)
    for name in ("wrangler.toml", "worker.js"):
        (hidden_parent / name).write_bytes((worker_dir / name).read_bytes())
    api = FakeAPI()
    deploy_worker(hidden_parent, transport=api.transport())
    assert set(api.uploads[0][2]) == {"worker.js"}


def test_node_modules_are_not_swept_up(worker_dir):
    deps = worker_dir / "node_modules" / "left-pad"
    deps.mkdir(parents=True)
    (deps / "index.js").write_text("module.exports = 1")
    api = FakeAPI()
    deploy_worker(worker_dir, transport=api.transport())
    assert set(api.uploads[0][2]) == {"worker.js", "lib.js"}


def test_refused_token_says_which_permission_is_missing(worker_dir):
    def handle(request):
        return httpx.Response(403, json={"success": False, "errors": []})

    with pytest.raises(PagesError, match="Workers Scripts: Edit"):
        deploy_worker(worker_dir, create_buckets=False,
                      transport=httpx.MockTransport(handle))


def test_missing_credentials(worker_dir, monkeypatch, tmp_path):
    monkeypatch.delenv("CLOUDFLARE_API_TOKEN")
    monkeypatch.setattr(pages, "ENV_FILE", tmp_path / "absent.env")
    with pytest.raises(PagesError, match="CLOUDFLARE_API_TOKEN"):
        deploy_worker(worker_dir)
