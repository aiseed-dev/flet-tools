# Changelog

## 0.3.1 (2026-08-28)

httpx 1.0 系を入れている環境では、0.3.0 は**どのコマンドも動きません**
(応答本文が読めずエラーになります)。その環境の方は 0.3.1 へ上げてください。
httpx 0.x のままなら 0.3.0 に問題はありません。

### Fixed

- **httpx 1.0 で応答本文が読めなかった**(weather からの報告)。1.0 の
  `Response` は `content` が解釈済みの包み(`Binary` や `JSON` 型)で、
  bytes ではありません。**生の本文は `body`** にあり、`read()` もない
  ——0.3.0 の集約層はそこを知らず、すべての応答で「本文が読めない」と
  して落ちていました。`raw()` に `body` の経路を足しています
  (`content` → `body` → `read()` の順に試し、どれでもなければ推測せず
  エラーにする方針は変えていません)
- 集約層の試験を追加しました(`tests/test_httpx_compat.py`)。両版の応答の
  形を再現して、bytes / str / dict が同じに取れることを固定します。
  `MockTransport` に依存しないので、**この試験は httpx 1.0 でも走ります**

### Added

- **R2: 上げた物を確かめる**(officework からの要望)。「上げたことに
  なっているが中身が違う」が配布でいちばん怖い形だ、という具体的な
  理由つきの依頼でした(2026-08-17 に、署名なしの物を「署名つき」と
  説明して公開しかけた事故があったとのこと)。
  - **常に検算します。** PUT に `Content-MD5` を付けるので、途中で
    壊れた本文はサーバーが受け取りません(400 BadDigest)。返ってきた
    `ETag` もローカルの MD5 と照合し、合わなければ成功と報告せずに
    失敗させます。ETag が返らない応答も「確かめられなかった」として
    失敗にします(黙って成功にしない)
  - **`--verify`** を付けると、転送のあとにバケットの一覧を取り直し、
    **一致として飛ばした物も含めて全部**を照合します。飛ばす判断の
    もとになった一覧そのものが古い場合があるためです。`--delete` と
    併用すると、消えていないオブジェクトも見つけます
  - 合わない物は 1 件ずつでなく**一覧で**報告します。1 個だけ壊れたのか
    全部なのかで、原因が違うためです(先頭 10 件と残りの数)
  - `--json` の結果に `verified`(照合した数)を追加

### Changed

- R2 の同期は、送る物が無くても局所の MD5 を数え上げます(`--verify` が
  飛ばした物まで見るため)。ファイル数の多い同期では、その分だけ
  読み込みが増えます

### Known issues

- 試験のうち `MockTransport` に依存する分は、httpx 1.0 では走りません
  (68 本中 33 本が失敗)。`MockTransport` が 1.0 で削除されているためで、
  製品コードの問題ではありません。集約層の試験は両版で走るので、
  版差の境目はそちらが見ています

## 0.3.0 (2026-08-28)

Pages と R2 は weather の実運用で使えています（3,132 ファイルのサイトを
Cloudflare Pages へ、R2 への同期も含めて）。**`worker deploy` は実物の
Cloudflare アカウントでまだ走らせていません**。cron とバインディングが
ダッシュボードに出るところまでは未確認です。

### Added

- **httpx の版差を 1 箇所に集約**（`_httpx_compat`）。httpx 1.0 は
  `Client(timeout=)` / `Response.text` / `Response.json()` /
  `raise_for_status()` を削除し、`status_code` と `content` の型も
  変えます（1.0.dev5 で実測）。
  - **依存に上限は付けません。** `httpx<1` と書けば当座はしのげますが、
    利用者の環境を縛り、他パッケージとの衝突も招きます。代わりに
    `hasattr(httpx, "timeout")` で版を検出して分岐します
  - 0.28.1 と 1.0.dev5 の両方で、実際に Cloudflare API を叩いて
    `status` / `raw` / `text` / `json_body` が同じ型・同じ値になることを
    確認しました
  - 応答に直接触るのは `_httpx_compat` だけです。1.0 が固まったら
    直すのはこのファイルで済みます

  - `Client` に指定した時間制限は `build_client` が控え、`_request` が
    それを使います。控えないと、アップロード用に 300 秒で作った
    `Client` が httpx 1.x では 120 秒で切れ、0.x とふるまいが変わります
  - 本文が読めない型で返ってきたら、見た目を文字列にして本文のふりを
    させず、その場でエラーにします（先で「壊れた JSON」として現れると
    原因が分からなくなるため）

### Known issues

- **テスト一式は httpx 1.0 では走りません。** `httpx.MockTransport` が
  1.0 で削除されており、偽サーバがそこに依存しています（25 件が失敗）。
  製品コードは両版で動きます。1.0 の後継 API が定まってから直します
- `pip install --pre cf-publish` は**依存にも `--pre` が効きます**。
  httpx 1.0.dev5 が入るので、安定版で使うなら `--pre` を付けないでください
  （0.3.0 は正式版なので、`--pre` は要りません）

## 0.3.0b1 (2026-08-27)

`worker deploy` を実物の Cloudflare アカウントに対してまだ1度も走らせて
いないため、**ベータとして出します**(`pip install --pre cf-publish`)。
API の応答はモックでしか見ていません。実際のデプロイで cron と
バインディングがダッシュボードに出るのを確認してから 0.3.0 にします。
Pages と R2 は 0.2.2 から変わっていません。

### Added

- **`cf-publish worker deploy DIR` — Worker のデプロイ**(weather からの
  要望)。スクリプト・バインディング・cron トリガーを、公開されている
  Workers API で上げます。`examples/form-worker/deploy.py`(実運用実績あり)
  の multipart の組み方を一般化したものです。
  - **`wrangler.toml` を既定値として読む**ので、既存の Worker は
    `cf-publish worker deploy DIR` だけで上がります(name / main /
    compatibility_date / `[triggers] crons` / `[[r2_buckets]]` / `[vars]`)。
    同じ項目のコマンドラインオプションが優先。読み手は Python 3.11 以降なら
    標準の `tomllib`、それ以前は内蔵の簡易リーダー(読めない書き方は推測せず
    エラー)。依存は増えていません
  - `--r2 バインディング=バケット`(無ければバケットを作成)、`--var`、
    `--secret 名前`(値は同名の環境変数から読み、出力しない)。
    アップロードはバインディングの一覧を丸ごと置き換えるため、
    `keep_bindings: ["secret_text"]` を常に付けて**再デプロイでシークレットが
    消えない**ようにしています
  - workers.dev の公開 URL は `--workers-dev` / `--no-workers-dev` を
    指定したときだけ変更します。既定では触りません(外に出さない収集用の
    Worker が、再デプロイしただけで公開されるのを防ぐため)
  - バンドラーは持ちません。`.js`/`.mjs`/`.json`/`.wasm`/`.txt` をモジュール
    としてそのまま上げます(相対 import は動く。npm パッケージは不可)。
    `node_modules` は除外。合計 10MiB で事前に止めます
  - `--dry-run` は API を1回も呼ばずに、上げる物・作るバケットを表示します

### Changed

- PyPI の説明文を3つのコマンドを表す文に更新
  (「Deploy to Cloudflare Pages, R2 and Workers from Python」)。
  キーワードに r2 / workers / wrangler を追加
- README(en/ja)の冒頭に**何をどのコマンドで公開するかの表**を追加。
  `r2` と `worker` は `cf-publish --help` からも辿れるようにした
  (サブコマンドの存在が help に出ておらず、気付けなかった)

## 0.2.2 (2026-07-17)

### Fixed

- **R2: SigV4 署名とリクエストのクエリ符号化を一致させた。** これまで
  `params=` 経由で httpx が独自にクエリを再符号化しており(空白が `%20`
  でなく `+` になる)、署名した正規化形と送信バイト列がずれるため、
  空白を含む `--prefix` などで RFC3986 どおりに検証するサーバから 403
  になり得た。正規化済みクエリ文字列をそのまま URL に載せるよう修正し、
  受信側で署名を再計算する回帰テストを追加。
- **`cf-publish --version` が一つ前のバージョンを表示していた。**
  pyproject.toml と `__init__.py` の二重定義が食い違っていたため
  (0.2.1 リリース時に `__init__.py` が 0.2.0 のまま)。hatch の
  dynamic version に一本化し、実体は `__init__.py` の `__version__` だけに。
- 関数スコープの `httpx.Client` を `with` で確実にクローズ
  (`upload_assets` と dry-run の照会)。

### Added

- **`examples/form-worker/`** — WordPress から分離した問い合わせフォームの
  受信箱(Cloudflare Worker + D1 + Turnstile)とデプロイスクリプト。
  bunko/forms から移設。セキュリティレビューを実施し、初回収録時点で
  次を修正済み: 既知フィールド名に一致しない正規送信が 400 になる問題、
  PULL_TOKEN の定数時間比較化と state ファイルの 0600 化(トークンは
  stdout に出さない)、ALLOWED_ORIGIN 未設定時の fail-closed 化、
  siteverify の hostname 突き合わせ、内部エラー文言の非開示、
  Content-Length の事前検査、破損 state ファイル時の明示エラー。

## 0.2.1 (2026-07-09)

### Fixed

- README: link to README.ja.md is now an absolute GitHub URL so it resolves
  on the PyPI project page (relative links only work on GitHub).

## 0.2.0 (2026-07-07)

### Added

- **`cf-publish r2 sync DIR BUCKET[/PREFIX]`** — sync a local folder to a
  Cloudflare R2 bucket over the S3-compatible API. AWS SigV4 implemented with
  the standard library (no boto3); diffing compares remote ETags against
  local MD5 so unchanged files are never re-sent; `--delete` removes
  remote-only objects; `--dry-run` / `--exclude` / `--quiet` / `--json` work
  like the Pages command. Credentials: R2_ACCESS_KEY_ID /
  R2_SECRET_ACCESS_KEY / CLOUDFLARE_ACCOUNT_ID. Single-PUT only (~5 GB/object).

## 0.1.1 (2026-07-06)

### Fixed

- **`_headers` / `_redirects` are now actually applied.** Root-level
  `_headers` and `_redirects` were uploaded as ordinary assets, so Cloudflare
  Pages served them as static files and silently ignored every rule. They are
  now excluded from the asset manifest and attached to the deployment request
  as form fields, matching wrangler's behaviour. Copies in subdirectories are
  still treated as ordinary assets. Found during the first real-world deploy
  (ecitizen.jp, 6,190 files).

## 0.1.0 — unreleased

Initial release, extracted from the aiseed-dev/website deploy tooling.

- Deploy a folder to Cloudflare Pages via the Direct Upload API
  (wrangler-compatible content hashing; unchanged files are never re-sent).
- Concurrent batch uploads (3 workers) with exponential backoff on 429/5xx
  and transport errors.
- Pre-flight validation of Pages limits (25 MiB/file, 20,000 files).
- `--dry-run`, `--exclude`, `--quiet`, `--json`, `--branch`, `--no-create`.
- Credentials from environment or `~/.config/cloudflare/pages.env`.
- Importable core (`cf_publish.deploy`) that raises `PagesError` and reports
  progress via callback — no prints, no exits.
