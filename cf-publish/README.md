# cf-publish

Deploy a local folder to **Cloudflare Pages** from Python — no wrangler,
no npm, no Node.js. One `pip install`, one command. The same CLI also syncs
data to **R2** and deploys **Workers**.

```bash
pip install cf-publish
export CLOUDFLARE_API_TOKEN=...    # token with "Cloudflare Pages: Edit"
export CLOUDFLARE_ACCOUNT_ID=...   # shown on the dashboard overview page
cf-publish ./public --project my-site
```

That's it. The contents of `./public` become the site. The project is created
on first deploy if it doesn't exist.

| | command | needs |
|---|---|---|
| static site → Pages | `cf-publish ./public --project my-site` | Cloudflare Pages: Edit |
| data → R2 | `cf-publish r2 sync ./data my-bucket/prefix` | R2 S3-API token |
| Worker + cron → Workers | `cf-publish worker deploy ./workers/collector` | Workers Scripts: Edit |

**What it's for**: publish a static site you built with Python (a blog, a
company site, docs) to the world without Node.js. The Pages free tier is
plenty for personal and small-business sites, global CDN and HTTPS included.
For large file distribution, pair it with R2 (free egress) via
`cf-publish r2 sync` — **a site that runs at $0/month**, hosting and
bandwidth included. When the site needs something collected or received on a
schedule, `cf-publish worker deploy` puts a Worker behind it, still without
Node.js on your machine.

日本語の説明は [README.ja.md](https://github.com/aiseed-dev/flet-tools/blob/main/cf-publish/README.ja.md) にあります。

## Why

The only official way to do a
[Direct Upload](https://developers.cloudflare.com/pages/get-started/direct-upload/)
deploy is wrangler, which drags in the whole Node.js toolchain. If your build
pipeline is Python (or just a folder of files), that's a lot of machinery for
one HTTP conversation. `cf-publish` implements the same upload protocol in
~300 lines of Python with two dependencies (`httpx`, `blake3`).

- **Content-addressed uploads** — files are hashed the same way wrangler
  hashes them, so unchanged files are never re-uploaded (fast repeat deploys,
  and the cache is shared with wrangler).
- **Concurrent uploads** with retry and exponential backoff on 429/5xx.
- **Pre-flight validation** of the Pages limits (25 MiB/file, 20,000
  files/deployment) before anything is sent.
- Root-level `_headers` / `_redirects` are attached to the deployment the
  way wrangler does it, so Pages actually parses and applies the rules
  (uploading them as plain assets would serve them as static files instead).

## Usage

```
cf-publish DIRECTORY --project NAME [options]

--branch BRANCH     'main' deploys to production, anything else gets a
                    preview URL (default: main)
--no-create         fail if the project doesn't exist instead of creating it
--exclude PATTERN   fnmatch pattern to skip, matched against the relative
                    path and the filename; repeatable (e.g. --exclude '*.map')
--dry-run           show what would be uploaded, deploy nothing
--quiet             print only the deployment URL
--json              print a JSON result (url, files, unique, uploaded,
                    duration, dry_run)
```

Progress goes to stderr, results to stdout, so both `--quiet` and `--json`
compose cleanly with shell pipelines and CI.

### Credentials

Environment variables win; otherwise `~/.config/cloudflare/pages.env` is read
(plain `KEY=VALUE` lines):

```
CLOUDFLARE_API_TOKEN=...
CLOUDFLARE_ACCOUNT_ID=...
```

Create the token at dash.cloudflare.com → My Profile → API Tokens with the
**Cloudflare Pages: Edit** permission. Nothing else is needed.

### As a library

```python
from cf_publish import deploy, PagesError

result = deploy("./public", "my-site", on_progress=print)
print(result.url, result.uploaded, result.duration)
```

The core raises `PagesError` on expected failures and never calls
`sys.exit()` or prints, so it embeds cleanly in build scripts and GUIs.

## Notes and caveats

- **Unofficial.** This project is not affiliated with Cloudflare. It speaks
  the same semi-official Direct Upload endpoints wrangler uses internally
  (`upload-token` / `check-missing` / `upload` / `upsert-hashes`). If
  Cloudflare changes them, fall back to wrangler or the Git integration —
  the hash algorithm is pinned by a fixed-value test so a breakage is caught
  loudly, not silently.
- Hidden files and directories (names starting with `.`) are never uploaded.
- Symlinks are followed and served as copies (Pages has no symlinks);
  cycles are detected and broken.

## R2 sync

```bash
export R2_ACCESS_KEY_ID=...        # R2 S3-API token (dashboard -> R2 -> Manage API Tokens)
export R2_SECRET_ACCESS_KEY=...    # NOT the Pages token
export CLOUDFLARE_ACCOUNT_ID=...
cf-publish r2 sync ./data my-bucket/some/prefix [--delete] [--verify] [--dry-run]
```

Diff-syncs a folder to an R2 bucket over the S3-compatible API — SigV4 is
implemented with the standard library, so still just two dependencies.
Unchanged files (remote ETag == local MD5) are skipped; `--delete` removes
remote objects that no longer exist locally. Single-PUT only, so objects are
capped at ~5 GB (no multipart yet). Pairs with the Pages command: site on
Pages, data on R2 (free egress), one CLI.

**Uploads are checked, not assumed.** Every PUT carries `Content-MD5`, so the
server refuses a body that arrived damaged, and the `ETag` it answers with is
compared against the local digest — a mismatch fails the sync instead of
being reported as a success. `--verify` adds a second pass: after the
transfer it lists the bucket again and compares *every* object, including the
ones skipped as unchanged, against the local digests. The confirmation then
comes from a fresh read rather than from the response that claimed success,
which is what you want before announcing a download.

## Workers

> **New in 0.3.0, and less travelled than the rest.** `worker deploy` has not
> yet been run against a live Cloudflare account: the API conversation is
> covered by tests against a mock, nothing more. Pages and R2 are unchanged
> from 0.2.2 and are in daily use.

```bash
export CLOUDFLARE_API_TOKEN=...    # needs "Workers Scripts: Edit" (the Pages token does not)
export CLOUDFLARE_ACCOUNT_ID=...
cf-publish worker deploy ./workers/collector
```

Uploads a Worker — script, bindings and cron triggers — over the documented
Workers API. `wrangler.toml` in the directory supplies the defaults, so an
existing Worker deploys with no flags at all:

```toml
name = "amedas-collector"
main = "worker.js"
compatibility_date = "2026-08-27"

[triggers]
crons = ["*/10 * * * *"]

[[r2_buckets]]
binding = "AMEDAS"
bucket_name = "weather-amedas"
```

Everything in the file can also be given on the command line, which wins:

```bash
cf-publish worker deploy ./workers/collector --name amedas-collector \
    --r2 AMEDAS=weather-amedas --cron '*/10 * * * *' --secret RUN_TOKEN
```

- **Bindings**: `--r2 BINDING=BUCKET` (the bucket is created if missing),
  `--var NAME=VALUE`, and `--secret NAME`, whose value is read from the
  environment variable of that name and never printed. Secrets already on the
  script survive a redeploy (`keep_bindings`), so you only pass a secret when
  setting or rotating it.
- **No bundler.** The `.js`/`.mjs`/`.json`/`.wasm`/`.txt` files in the
  directory are uploaded as modules, so relative imports work and npm
  packages do not. `node_modules` is skipped.
- **The workers.dev URL is left exactly as it is** unless you pass
  `--workers-dev` / `--no-workers-dev`. A private collector should not sprout
  a public URL because it was redeployed.
- `wrangler.toml` is read with the standard `tomllib` on Python 3.11+, and
  with a small built-in reader below that (it raises rather than guessing).
  Environment sections (`[env.production]`) are ignored.

## Roadmap

- R2 multipart uploads (>5 GB objects).
- More binding types for Workers (KV, D1, queues, service bindings).

Deployment list / rollback is intentionally out of scope: the Cloudflare
dashboard ships both ("Rollback to this deployment"), so a CLI duplicate
adds nothing.

## License

MIT
