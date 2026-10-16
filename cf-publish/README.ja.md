# cf-publish

ローカルのフォルダを **Cloudflare Pages** へ直接デプロイする Python 製 CLI。
wrangler も npm も Node.js も不要。`pip install` ひとつで使える。
同じ CLI で **R2** への同期と **Workers** のデプロイもできる。

```bash
pip install cf-publish
export CLOUDFLARE_API_TOKEN=...    # 「Cloudflare Pages: 編集」権限のトークン
export CLOUDFLARE_ACCOUNT_ID=...   # ダッシュボード概要ページに表示される ID
cf-publish ./public --project my-site
```

`./public` の中身がそのままサイトになる。プロジェクトが無ければ初回に作成される。

| | コマンド | 要る権限 |
|---|---|---|
| 静的サイト → Pages | `cf-publish ./public --project my-site` | Cloudflare Pages: 編集 |
| データ → R2 | `cf-publish r2 sync ./data バケット/プレフィックス` | R2 の S3 互換 API トークン |
| Worker と cron → Workers | `cf-publish worker deploy ./workers/collector` | Workers Scripts: 編集 |

**何ができるか**: Python でビルドした静的サイト(ブログ・会社サイト・
ドキュメント)を、Node.js なしで世界に公開する。Pages の無料枠は個人や
中小のサイトに十分で、CDN 配信と HTTPS も込み。大きなファイルの配布は
R2(下り転送料が無料)を `cf-publish r2 sync` で併用——**サーバー代も
転送料も月0円**でサイトが回る。定期的な収集や受信が要るなら、
`cf-publish worker deploy` で Worker を置ける。ここでも Node.js は要らない。

## なぜ作ったか

Direct Upload デプロイの公式手段は wrangler（Node.js 一式）だけ。ビルドが
Python のサイト（あるいはただのフォルダ）のために Node を入れるのは大げさなので、
wrangler と同じアップロードプロトコルを Python ~300 行・依存 2 つ
（httpx / blake3）で実装した。

- **内容アドレスなアップロード** — wrangler と同一方式のハッシュなので、
  変更のないファイルは二度と送られない（再デプロイが速い）
- 429/5xx への指数バックオフつき**並列アップロード**
- 送信前に Pages の制限（25 MiB/ファイル、20,000 ファイル/デプロイ）を**事前検証**
- ルート直下の `_headers` / `_redirects` は wrangler と同じ方式でデプロイに添付され、Pages がルールとして解釈・適用します。

## 使い方

```
cf-publish 公開ディレクトリ --project 名前 [オプション]

--branch BRANCH     main は本番、それ以外はプレビュー URL（既定: main）
--no-create         プロジェクトが無いとき作らずエラーにする
--exclude PATTERN   除外パターン（fnmatch。相対パスとファイル名に適用、複数可）
--dry-run           何が送られるかの表示だけで、デプロイしない
--quiet             デプロイ URL だけを表示
--json              結果を JSON で表示（url / files / unique / uploaded / duration）
```

進捗は stderr、結果は stdout に出るので、CI やパイプで扱いやすい。

### 認証情報

環境変数が優先。無ければ `~/.config/cloudflare/pages.env`（`KEY=VALUE` 形式）を読む。
トークンは dash.cloudflare.com → My Profile → API Tokens で
**Cloudflare Pages: 編集** 権限のものを作る。

### ライブラリとして

```python
from cf_publish import deploy, PagesError

result = deploy("./public", "my-site", on_progress=print)
print(result.url, result.uploaded, result.duration)
```

コアは `sys.exit()` も `print()` もせず、想定エラーは `PagesError` を投げる。

## 注意

- **非公式ツール**。Cloudflare とは無関係。wrangler が内部で使う半公式 API を
  話しているため、API が変わったら wrangler か Git 連携へ退避すること。
  ハッシュ方式は固定値テストで釘付けにしてあり、変更があれば静かに壊れず
  テストで検知できる。
- 隠しファイル・隠しディレクトリ（`.` 始まり）は送られない。
- シンボリックリンクは実体のコピーとして配信される（循環は検知して停止）。

## R2 同期

```bash
export R2_ACCESS_KEY_ID=...        # R2 の S3 互換 API トークン（Pages トークンとは別）
export R2_SECRET_ACCESS_KEY=...
export CLOUDFLARE_ACCOUNT_ID=...
cf-publish r2 sync ./data バケット名/プレフィックス [--delete] [--verify] [--dry-run]
```

S3 互換 API での差分同期。SigV4 は標準ライブラリ実装なので依存は増えていない。
遠隔 ETag と ローカル MD5 が一致するファイルはスキップ、`--delete` でローカルに
無い遠隔オブジェクトを削除。単一 PUT のみ（〜5GB、マルチパート未対応）。
「サイトは Pages、データは R2」が 1 つの CLI で完結する。

**上げた物は、上げっぱなしにせず確かめます。** PUT には常に `Content-MD5`
を付けるので、途中で壊れた本文はサーバー側が受け取りません。返ってきた
`ETag` もローカルの MD5 と照合し、合わなければ**成功と報告せずに失敗**
させます。`--verify` を付けると、転送のあとにもう一度バケットの一覧を
取り、**一致として飛ばした物も含めて全部**を照合します。確認の根拠が
「成功と言った当の応答」ではなく「取り直した値」になるので、配布物を
公開する前の確認に向きます。

## Workers

> **0.3.0 で入ったばかりです。** `worker deploy` は実物の Cloudflare
> アカウントに対してまだ1度も走らせていません（API のやり取りは、モックに
> 対するテストで確認しているだけです）。Pages と R2 は 0.2.2 から変わって
> おらず、日常的に使っています。

```bash
export CLOUDFLARE_API_TOKEN=...    # 「Workers Scripts: 編集」権限が要る（Pages トークンには無い）
export CLOUDFLARE_ACCOUNT_ID=...
cf-publish worker deploy ./workers/collector
```

Worker のスクリプト・バインディング・cron トリガーを、公開されている Workers
API でデプロイします。ディレクトリにある `wrangler.toml` を既定値として読むので、
すでにある Worker はオプション無しでそのまま上がります。

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

同じ内容はコマンドラインでも指定でき、そちらが優先されます。

```bash
cf-publish worker deploy ./workers/collector --name amedas-collector \
    --r2 AMEDAS=weather-amedas --cron '*/10 * * * *' --secret RUN_TOKEN
```

- **バインディング**: `--r2 バインディング名=バケット名`（バケットが無ければ
  作成）、`--var 名前=値`、`--secret 名前`。シークレットの値は同名の環境変数
  から読み、画面にもログにも出しません。既にスクリプトに設定済みの
  シークレットは再デプロイでも消えない（`keep_bindings`）ので、渡すのは
  新規設定と交換のときだけです。
- **バンドラーはありません。** ディレクトリ内の `.js`/`.mjs`/`.json`/`.wasm`/
  `.txt` をモジュールとしてそのまま上げます。相対 import は動きますが、npm
  パッケージは使えません。`node_modules` は除外します。
- **workers.dev の公開 URL は触りません**（`--workers-dev` /
  `--no-workers-dev` を指定したときだけ変更）。外に出さない収集用の Worker が、
  再デプロイしただけで公開されてしまうのを防ぐためです。
- `wrangler.toml` は Python 3.11 以降なら標準の `tomllib`、それ以前は内蔵の
  簡易リーダーで読みます（読めない書き方は推測せずエラーにします）。
  `[env.production]` のような環境別の節は無視します。

## ロードマップ

- R2 マルチパートアップロード（5GB 超）
- Workers のバインディング拡充（KV・D1・キュー・サービスバインディング）

デプロイ一覧/ロールバックは作りません: Cloudflare ダッシュボードに標準装備
（Rollback to this deployment）されており、CLI に重複実装する価値がないためです。

## ライセンス

MIT
