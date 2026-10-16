"""Deploy a Cloudflare Worker — script, bindings and cron triggers, no wrangler.

Same design contract as :mod:`cf_publish.pages`: UI-agnostic, returns values,
raises :class:`PagesError`, reports progress through ``on_progress``.

Unlike the Pages asset endpoints, everything here is the *documented* Workers
API: ``PUT /accounts/{id}/workers/scripts/{name}`` (multipart — one metadata
part plus one part per module), ``PUT .../schedules`` for cron triggers, and
the R2 bucket endpoints. The one semi-documented field is ``keep_bindings``:
an upload replaces the binding list wholesale, so without it every redeploy
would silently delete the script's secrets.

There is no bundler here. The modules in the directory are uploaded as they
are, so relative imports between them work but npm packages do not — which
is the shape of a collector/webhook Worker, the case this exists for.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Optional

import httpx

from ._httpx_compat import build_client, json_body, status
from .pages import (API, ENV_FILE, PagesError, ProgressFn, _excluded, _noop,
                    _request, _user_agent, load_env_file)

# Module types Cloudflare accepts in a script upload. A file whose suffix is
# not here is not part of the Worker (wrangler.toml itself, README, ...).
MODULE_TYPES = {
    ".js": "application/javascript+module",
    ".mjs": "application/javascript+module",
    ".json": "application/json",
    ".wasm": "application/wasm",
    ".txt": "text/plain",
}
# Default exclusions: an unbundled Worker directory has no business shipping
# a dependency tree, and sweeping one up would silently blow the size limit.
DEFAULT_EXCLUDE = ("node_modules/*", "*/node_modules/*")
# Binding kinds wrangler.toml can declare that this tool does not send. Silently
# ignoring one would deploy a Worker that breaks at runtime, so they raise.
UNSUPPORTED_BINDINGS = (
    "kv_namespaces", "d1_databases", "queues", "durable_objects", "services",
    "hyperdrive", "vectorize", "analytics_engine_datasets", "browser", "ai",
    "mtls_certificates", "dispatch_namespaces", "send_email", "assets",
)
MAX_SCRIPT_BYTES = 10 * 1024 * 1024  # Workers paid limit (free is 3 MiB gzipped)
DEFAULT_COMPAT_DATE = "2024-11-01"
CONFIG_FILE = "wrangler.toml"


@dataclass
class WorkerResult:
    name: str  # script name
    main: str  # entry module, relative to the directory
    modules: int  # modules uploaded
    bindings: int  # bindings sent (secrets counted, never shown)
    crons: "list[str]" = field(default_factory=list)
    buckets_created: "list[str]" = field(default_factory=list)
    url: str = ""  # workers.dev URL, only when --workers-dev was asked for
    duration: float = 0.0
    dry_run: bool = False


# ---------------------------------------------------------------- config

def _strip_comment(value: str) -> str:
    """Drop a trailing ``# comment``, respecting quoted strings."""
    quote = ""
    for i, ch in enumerate(value):
        if quote:
            if ch == quote:
                quote = ""
        elif ch in "\"'":
            quote = ch
        elif ch == "#":
            return value[:i]
    return value


def _scalar(raw: str, lineno: int):
    raw = raw.strip()
    if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in "\"'":
        return raw[1:-1]
    if raw in ("true", "false"):
        return raw == "true"
    try:
        return int(raw)
    except ValueError:
        raise PagesError(
            f"{CONFIG_FILE} line {lineno}: cannot read the value {raw!r} "
            f"(this fallback reader handles strings, numbers, booleans and "
            f"arrays of them). Pass the value as a command-line flag, or run "
            f"on Python 3.11+ where the standard tomllib is used."
        ) from None


def parse_toml_subset(text: str) -> dict:
    """Read the subset of TOML that wrangler.toml uses.

    Used only when neither ``tomllib`` (Python 3.11+) nor ``tomli`` is
    importable. Anything it cannot read raises rather than being skipped: a
    silently misread config would deploy the wrong bindings.
    """
    root: dict = {}
    current = root
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        line = _strip_comment(lines[i]).strip()
        lineno = i + 1
        i += 1
        if not line:
            continue
        if line.startswith("[["):
            if not line.endswith("]]"):
                raise PagesError(f"{CONFIG_FILE} line {lineno}: unterminated [[table]]")
            key = line[2:-2].strip()
            root.setdefault(key, []).append({})
            current = root[key][-1]
            continue
        if line.startswith("["):
            if not line.endswith("]"):
                raise PagesError(f"{CONFIG_FILE} line {lineno}: unterminated [table]")
            key = line[1:-1].strip()
            current = root.setdefault(key, {})
            continue
        if "=" not in line:
            raise PagesError(f"{CONFIG_FILE} line {lineno}: cannot read {line!r}")
        key, _, raw = line.partition("=")
        key, raw = key.strip(), raw.strip()
        if raw.startswith("{"):
            raise PagesError(
                f"{CONFIG_FILE} line {lineno}: inline tables are not supported by "
                f"this fallback reader. Run on Python 3.11+ or `pip install tomli`.")
        if raw.startswith("["):
            while "]" not in raw and i < len(lines):
                raw += " " + _strip_comment(lines[i]).strip()
                i += 1
            if "]" not in raw:
                raise PagesError(f"{CONFIG_FILE} line {lineno}: unterminated array")
            body = raw[raw.index("[") + 1:raw.rindex("]")]
            current[key] = [_scalar(item, lineno)
                            for item in body.split(",") if item.strip()]
        else:
            current[key] = _scalar(raw, lineno)
    return root


def read_config(path: Path) -> dict:
    """Parse wrangler.toml. Prefers the standard library reader when present."""
    text = path.read_text(encoding="utf-8")
    try:
        import tomllib  # Python 3.11+
    except ModuleNotFoundError:
        try:
            import tomli as tomllib  # type: ignore[no-redef]
        except ModuleNotFoundError:
            return parse_toml_subset(text)
    try:
        return tomllib.loads(text)
    except Exception as exc:  # tomllib.TOMLDecodeError
        raise PagesError(f"{path}: {exc}") from None


def config_defaults(data: dict) -> dict:
    """Pull the fields we act on out of a parsed wrangler.toml.

    Environment sections (``[env.production]``) and wrangler-only keys are
    ignored. Binding kinds this tool cannot send raise instead: a Worker
    deployed without the KV namespace it declares would fail at runtime,
    somewhere else, later.
    """
    unsupported = sorted(k for k in UNSUPPORTED_BINDINGS if data.get(k))
    if unsupported:
        raise PagesError(
            f"{CONFIG_FILE} declares {', '.join(unsupported)}, which cf-publish "
            f"cannot bind yet (it handles r2_buckets and vars). Deploy this "
            f"Worker with wrangler, or open an issue for the binding you need.")
    triggers = data.get("triggers") or {}
    r2: dict[str, str] = {}
    for bucket in data.get("r2_buckets") or []:
        binding, name = bucket.get("binding"), bucket.get("bucket_name")
        if not binding or not name:
            raise PagesError(
                f"{CONFIG_FILE}: every [[r2_buckets]] needs `binding` and "
                f"`bucket_name` (got {bucket!r})")
        r2[binding] = name
    return {
        "name": data.get("name"),
        "main": data.get("main"),
        "compatibility_date": data.get("compatibility_date"),
        "compatibility_flags": list(data.get("compatibility_flags") or []),
        "crons": list(triggers.get("crons") or []),
        "r2": r2,
        "vars": dict(data.get("vars") or {}),
    }


def parse_pair(text: str, what: str) -> "tuple[str, str]":
    name, sep, value = text.partition("=")
    if not sep or not name.strip():
        raise PagesError(f"--{what} expects NAME=VALUE, got {text!r}")
    return name.strip(), value


# ---------------------------------------------------------------- client

class Workers:
    """Thin client for the Workers script, cron and R2 bucket endpoints."""

    def __init__(self, account_id: str, token: str,
                 transport: Optional[httpx.BaseTransport] = None):
        self.account = f"{API}/accounts/{account_id}"
        self.client = build_client(
            timeout=120.0,
            headers={"Authorization": f"Bearer {token}",
                     "User-Agent": _user_agent()},
            transport=transport,
        )

    def _ok(self, resp: httpx.Response, action: str) -> dict:
        if status(resp) in (401, 403):
            raise PagesError(
                f"{action}: HTTP {status(resp)} — the API token was refused. "
                f"Uploading a Worker needs the 'Workers Scripts: Edit' permission "
                f"(the Pages token does not carry it); creating R2 buckets needs "
                f"'Workers R2 Storage: Edit'.")
        try:
            body = json_body(resp)
        except ValueError:
            raise PagesError(
                f"{action}: non-JSON response (HTTP {status(resp)})") from None
        if not body.get("success"):
            raise PagesError(
                f"{action}: API error\n"
                f"{json.dumps(body.get('errors'), ensure_ascii=False)}")
        return body.get("result")

    def upload(self, name: str, metadata: dict,
               modules: "dict[str, tuple[bytes, str]]") -> dict:
        """PUT the script. The metadata part must come first, and the part name
        of each module must equal the module specifier used in imports."""
        files: dict = {
            "metadata": (None, json.dumps(metadata).encode(), "application/json")}
        for mod, (data, ctype) in modules.items():
            files[mod] = (mod, data, ctype)
        return self._ok(
            _request(self.client, "PUT",
                     f"{self.account}/workers/scripts/{name}", files=files),
            f"upload {name}")

    def set_crons(self, name: str, crons: "list[str]") -> None:
        self._ok(
            _request(self.client, "PUT",
                     f"{self.account}/workers/scripts/{name}/schedules",
                     json=[{"cron": c} for c in crons]),
            f"set cron triggers on {name}")

    def bucket_exists(self, bucket: str) -> bool:
        resp = _request(self.client, "GET", f"{self.account}/r2/buckets/{bucket}")
        if status(resp) == 404:
            return False
        self._ok(resp, f"look up bucket {bucket}")
        return True

    def create_bucket(self, bucket: str) -> None:
        self._ok(
            _request(self.client, "POST", f"{self.account}/r2/buckets",
                     json={"name": bucket}),
            f"create bucket {bucket}")

    def set_workers_dev(self, name: str, enabled: bool) -> None:
        self._ok(
            _request(self.client, "POST",
                     f"{self.account}/workers/scripts/{name}/subdomain",
                     json={"enabled": enabled}),
            f"{'enable' if enabled else 'disable'} the workers.dev URL")

    def subdomain(self) -> str:
        result = self._ok(
            _request(self.client, "GET", f"{self.account}/workers/subdomain"),
            "read the workers.dev subdomain")
        return (result or {}).get("subdomain") or ""


# ---------------------------------------------------------------- deploy

def collect_modules(root: Path, main: str,
                    exclude: Iterable[str] = ()) -> "dict[str, tuple[bytes, str]]":
    """Map module specifier -> (bytes, content type) for the whole directory."""
    patterns = tuple(exclude) + DEFAULT_EXCLUDE
    modules: dict[str, tuple[bytes, str]] = {}
    total = 0
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root)  # 隠し判定は root より下だけを見る
        rel = relative.as_posix()          # (~/.config/... の下でも消えないように)
        if not path.is_file() or any(part.startswith(".") for part in relative.parts):
            continue
        ctype = MODULE_TYPES.get(path.suffix)
        if ctype is None or _excluded(rel, patterns):
            continue
        data = path.read_bytes()
        total += len(data)
        modules[rel] = (data, ctype)
    if main not in modules:
        raise PagesError(
            f"entry module not found: {main} (in {root}). "
            f"Modules seen: {', '.join(modules) or 'none'}")
    if total > MAX_SCRIPT_BYTES:
        raise PagesError(
            f"the modules total {total // 1024} KiB, over the "
            f"{MAX_SCRIPT_BYTES // (1024 * 1024)} MiB Workers script limit")
    # Only the module format is uploaded here. The old service-worker format
    # (addEventListener) would upload without complaint and then do nothing at
    # runtime, which is the worst way to find out.
    entry = modules[main][0].decode("utf-8", "replace")
    if "export default" not in entry and "addEventListener(" in entry:
        raise PagesError(
            f"{main} looks like the old service-worker format "
            f"(addEventListener). cf-publish uploads module-format Workers: "
            f"use `export default {{ async fetch(...) {{}} }}`.")
    return modules


def _resolve_main(root: Path, main: "str | None", defaults: dict) -> str:
    for candidate in (main, defaults.get("main")):
        if candidate:
            return Path(candidate).as_posix()
    if (root / "worker.js").is_file():
        return "worker.js"
    scripts = [p.name for p in sorted(root.glob("*.js"))]
    if len(scripts) == 1:
        return scripts[0]
    raise PagesError(
        f"cannot tell which module is the entry point in {root}: "
        f"pass --main, or set `main` in {CONFIG_FILE} "
        f"(candidates: {', '.join(scripts) or 'none'})")


def deploy_worker(directory: "str | Path", *, name: "str | None" = None,
                  main: "str | None" = None,
                  compatibility_date: "str | None" = None,
                  compatibility_flags: Iterable[str] = (),
                  r2: "Iterable[tuple[str, str]]" = (),
                  variables: "Iterable[tuple[str, str]]" = (),
                  secrets: Iterable[str] = (),
                  crons: "Iterable[str] | None" = None,
                  create_buckets: bool = True,
                  workers_dev: "bool | None" = None,
                  exclude: Iterable[str] = (),
                  dry_run: bool = False, on_progress: ProgressFn = _noop,
                  transport: Optional[httpx.BaseTransport] = None) -> WorkerResult:
    """Deploy the Worker in ``directory`` and return a :class:`WorkerResult`.

    ``wrangler.toml`` next to the modules supplies the defaults (name, main,
    compatibility date, cron triggers, R2 bindings, plain vars); the arguments
    here win. R2 bindings and vars are merged by binding name; ``crons``, when
    given, replaces the ones from the file.

    Secrets are named, not valued: each name in ``secrets`` is read from the
    environment (or ``~/.config/cloudflare/pages.env``) and never printed.
    Secrets already on the script survive a redeploy even when not listed.

    The workers.dev URL is left exactly as it is unless ``workers_dev`` is
    True or False — a collector Worker that is not meant to face the public
    should not sprout a public URL because it was redeployed.

    Credentials: ``CLOUDFLARE_API_TOKEN`` with **Workers Scripts: Edit** (plus
    **Workers R2 Storage: Edit** to create buckets) and ``CLOUDFLARE_ACCOUNT_ID``.
    """
    started = time.monotonic()
    load_env_file()
    token = os.environ.get("CLOUDFLARE_API_TOKEN")
    account = os.environ.get("CLOUDFLARE_ACCOUNT_ID")
    if not token or not account:
        raise PagesError(
            "set CLOUDFLARE_API_TOKEN (a token with the 'Workers Scripts: Edit' "
            f"permission) and CLOUDFLARE_ACCOUNT_ID in the environment or in {ENV_FILE}"
        )

    root = Path(directory)
    if not root.is_dir():
        raise PagesError(f"not a directory: {root}")

    config = root / CONFIG_FILE
    if config.is_file():
        defaults = config_defaults(read_config(config))
        on_progress(f"read {CONFIG_FILE}")
    else:
        defaults = config_defaults({})

    script = name or defaults.get("name")
    if not script:
        raise PagesError(
            f"no script name: pass --name, or set `name` in {CONFIG_FILE}")
    entry = _resolve_main(root, main, defaults)
    modules = collect_modules(root, entry, exclude)

    bucket_bindings = dict(defaults["r2"])
    bucket_bindings.update(dict(r2))
    plain_vars = dict(defaults["vars"])
    plain_vars.update(dict(variables))
    schedule = list(defaults["crons"] if crons is None else crons)

    bindings: list[dict] = []
    for binding, bucket in bucket_bindings.items():
        bindings.append({"type": "r2_bucket", "name": binding, "bucket_name": bucket})
    for key, value in plain_vars.items():
        bindings.append({"type": "plain_text", "name": key, "text": str(value)})
    for key in secrets:
        value = os.environ.get(key)
        if not value:
            raise PagesError(
                f"secret {key} is not set: put it in the environment or in "
                f"{ENV_FILE} (its value is never printed or logged)")
        bindings.append({"type": "secret_text", "name": key, "text": value})

    metadata = {
        "main_module": entry,
        "compatibility_date": (compatibility_date
                               or defaults.get("compatibility_date")
                               or DEFAULT_COMPAT_DATE),
        "compatibility_flags": list(compatibility_flags
                                    or defaults["compatibility_flags"]),
        "bindings": bindings,
        # An upload replaces the binding list wholesale. Secrets cannot be read
        # back, so without this every redeploy would quietly wipe them.
        "keep_bindings": ["secret_text"],
    }

    named = ", ".join(f"{b['type']}:{b['name']}" for b in bindings) or "none"
    on_progress(f"{script}: {len(modules)} module{'s' if len(modules) != 1 else ''}"
                f" (entry {entry}), bindings {named}")
    if schedule:
        on_progress(f"cron: {', '.join(schedule)}")

    if dry_run:
        for mod in modules:
            on_progress(f"  would upload {mod}")
        for bucket in sorted(set(bucket_bindings.values())):
            on_progress(f"  would ensure bucket {bucket}")
        on_progress("dry run: nothing was uploaded or changed")
        return WorkerResult(name=script, main=entry, modules=len(modules),
                            bindings=len(bindings), crons=schedule,
                            duration=time.monotonic() - started, dry_run=True)

    api = Workers(account, token, transport=transport)

    created: list[str] = []
    if create_buckets:
        for bucket in sorted(set(bucket_bindings.values())):
            if not api.bucket_exists(bucket):
                api.create_bucket(bucket)
                created.append(bucket)
                on_progress(f"created bucket: {bucket}")

    api.upload(script, metadata, modules)
    on_progress(f"uploaded {script}")

    if schedule:
        api.set_crons(script, schedule)
        on_progress(f"cron triggers set: {len(schedule)}")

    url = ""
    if workers_dev is not None:
        api.set_workers_dev(script, workers_dev)
        if workers_dev:
            sub = api.subdomain()
            url = f"https://{script}.{sub}.workers.dev" if sub else ""
            on_progress(url or "workers.dev enabled, but no subdomain is "
                               "registered on this account yet")
        else:
            on_progress("workers.dev URL disabled")

    return WorkerResult(name=script, main=entry, modules=len(modules),
                        bindings=len(bindings), crons=schedule,
                        buckets_created=created, url=url,
                        duration=time.monotonic() - started)
