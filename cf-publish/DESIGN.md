# cf-publish — 設計書（独立パッケージ化・PyPI / conda-forge 公開）

作成: 2026-07-06。website リポジトリ `tools/cloudflare_pages_deploy.py`（参照実装・
実運用済み）と `apps/cf-publish/pypi/`（パッケージ試作）を種に、独立配布物にする。

## 1. やる価値の確認（実測 2026-07-06）

- **公式手段は wrangler（Node.js）だけ**。「フォルダを Cloudflare Pages に上げたい
  だけなのに npm 一式が要る」は Python 圏の実在する不満。
- **PyPI に競合が存在しない**: `cf-publish` `cloudflare-pages` `cloudflare-pages-deploy`
  `pages-deploy` `cf-pages` `cfdeploy` すべて 404（未登録）を確認。
- 公式 `cloudflare` SDK は Pages の Direct Upload（upload-token / check-missing /
  upload / upsert-hashes）を**カバーしていない**。ニッチは空いている。
- 依存 2 つ（httpx, blake3）とも conda-forge に既存 → noarch レシピが素直に通る。

**名前は `cf-publish`**（空き確認済み）。`cloudflare-` プレフィックスは公式製品と
誤認されうるので避け、README に unofficial を明記する。

## 2. リポジトリ構成（この dev/cf-publish/ が新リポジトリになる）

```
cf-publish/
├── pyproject.toml          # hatchling / MIT / console script: cf-publish
├── README.md               # 英語（PyPI の顔）
├── README.ja.md            # 日本語
├── LICENSE                 # MIT
├── CHANGELOG.md
├── src/cf_publish/
│   ├── __init__.py         # __version__ と公開 API（deploy, PagesError）
│   ├── pages.py            # UI 非依存コア（試作版を継承・強化）
│   └── cli.py              # argparse CLI
├── tests/                  # httpx.MockTransport ベース（実アカウント不要）
│   ├── test_hash.py        # wrangler 互換ハッシュの固定値テスト
│   ├── test_collect.py     # 収集・除外・上限・リンク循環
│   └── test_deploy.py      # API 会話全体のモックテスト
└── .github/workflows/
    ├── test.yml            # pytest（3.9–3.13）
    └── publish.yml         # タグ push → PyPI Trusted Publishing（OIDC）
```

website リポジトリ側は `tools/cloudflare_pages_deploy.py` を当面残す（実運用の
退路）。安定後に `pip install cf-publish` へ置き換え、`apps/cf-publish/pypi/` は
「独立リポジトリへ移動した」旨の README だけ残す。

## 3. 「便利にして」の中身（v0.1.0 スコープ）

試作版からの強化点。コアの「値を返す / PagesError を投げる / on_progress 通知」
の設計はそのまま。

| # | 機能 | 内容 |
|---|------|------|
| 1 | `--dry-run` | 収集・ハッシュ・check-missing まで実行し、何が送られるかを表示して終了（website の「確認を挟む」運用と相性がよい） |
| 2 | `--exclude PATTERN`（複数可） | fnmatch 形式。既定の除外は隠しファイルのみ（現行踏襲）。`_headers` / `_redirects` はそのまま通す |
| 3 | リトライ | 429 / 5xx / タイムアウトに指数バックオフ（2→4→8 秒、3 回）。ECMWF 取得で実証済みのパターン |
| 4 | 並列アップロード | バッチを 3 並列で送る（wrangler と同じ並列度）。大サイトで体感数倍 |
| 5 | 事前検証 | Pages の制限をアップロード前に検査: 25MiB/ファイル、20,000 ファイル/デプロイ、パス長 |
| 6 | CI 向け出力 | `--quiet`（URL のみ標準出力）と `--json`（url / files / uploaded / duration）。終了コードで成否 |
| 7 | User-Agent | `cf-publish/{version} (+repo URL)` を名乗る（正直に名乗る方針） |
| 8 | 認証の説明改善 | トークン権限（Cloudflare Pages: Edit）・Account ID の場所・`~/.config/cloudflare/pages.env` を `--help` と README に明記 |

**やらないこと（v0.1）**: プロジェクト削除・ロールバック・カスタムドメイン設定・
ビルド連携。Unix 的に「1 フォルダを 1 プロジェクトへ上げる」だけに絞る。

## 4. ロードマップ（v0.2 以降・参考）

- **R2 サブコマンド** `cf-publish r2 sync <dir> <bucket>[/prefix]`:
  S3 互換 API（SigV4 は hashlib/hmac で書ける。追加依存なし）。
  Pages の 25MiB 制限を超えるデータ配布（気象 NetCDF など）はこちらが受け皿。
  「サイトは Pages、データは R2」を 1 つの CLI で完結させる。
- ~~デプロイ一覧 / ロールバック~~ **作らない**（2026-07-09 決定）:
  Cloudflare ダッシュボードに標準装備（Rollback to this deployment）されて
  おり、CLI に重複実装する価値がない。本キットの範囲は「上げる」まで。

## 5. リスクと退路

Direct Upload API は**半公式**（wrangler の内部プロトコル。`upload-token` 以外の
assets 系は公式リファレンス外）。方針:

- README に明記: 「wrangler が使うのと同じ API。壊れたら wrangler か Git 連携へ」
- ハッシュ方式（blake3(base64+拡張子) 先頭 32 桁）は固定値テストで釘付けにし、
  wrangler 側の変更に気づけるようにする
- 週次で動かす CI カナリア（実デプロイはせず check-missing まで）は任意・後回し

## 6. 公開手順（外部作業はユーザー、準備はローカルで完了させる）

1. **ローカル（こちらで実施）**: 上記構成一式＋テスト＋`uv build` で wheel/sdist
   生成・インストール・`--help` 起動まで検証
2. **ユーザー**: GitHub に `aiseed-dev/cf-publish` を作成し push
3. **ユーザー**: PyPI で Trusted Publishing を設定（アカウント → Publishing →
   GitHub `aiseed-dev/cf-publish` の `publish.yml` を登録）→ タグ `v0.1.0` を push
   すると CI が公開。手動なら `uv publish`
4. **conda-forge（PyPI 公開後）**: `grayskull pypi cf-publish` でレシピ生成 →
   `conda-forge/staged-recipes` へ PR（noarch: python、deps とも conda-forge 済み）。
   レビューは通常数日〜数週。マージ後は feedstock が自動で追随

## 7. 判断が必要な点

- パッケージ名 `cf-publish` で確定してよいか（空きは確認済み）
- GitHub の置き場所は aiseed-dev org でよいか
- v0.1 に R2 を入れず Pages 専念でよいか（推奨: 入れない）

## 8. v0.2: `cf-publish r2 sync`（2026-07-07 着手）

`cf-publish r2 sync <dir> <bucket>[/prefix]` — ローカルディレクトリを R2 バケットへ
差分同期する。Pages の 25MiB 制限を超えるデータ配布（気象 NetCDF・タイル・チャート）
の受け皿。rclone の置き換えが目的なので機能は sync に絞る。

- **認証**: R2 の S3 互換 API トークン（Pages トークンとは別物）。
  `R2_ACCESS_KEY_ID` / `R2_SECRET_ACCESS_KEY` ＋ `CLOUDFLARE_ACCOUNT_ID` を
  環境変数か ~/.config/cloudflare/pages.env から読む
- **SigV4 を標準ライブラリで実装**（hashlib/hmac。追加依存なし。転送は既存の httpx）
- **差分判定**: ListObjectsV2（ページネーション対応）で遠隔の ETag を取り、
  ローカル MD5 と比較（R2 の単一 PUT の ETag は MD5）。一致はスキップ
- **削除**: `--delete` 指定時のみ、ローカルに無い遠隔オブジェクトを削除
  （予報ランの世代交代に必要。既定は削除しない安全側）
- **並列 PUT**（3 並列・指数バックオフは Pages 側と共通の _request を再利用）
- `--dry-run` / `--exclude` / `--quiet` / `--json` は Pages 側と同じ意味
- **制限**: 単一 PUT のみ（〜5GB）。マルチパートは対象外と README に明記
- CLI 構成: `cf-publish <dir> --project ...`（従来・後方互換）に加え
  `cf-publish r2 sync ...` サブコマンド
- テスト: SigV4 は AWS 公式テストベクタで固定、sync は MockTransport で
  ListObjectsV2(XML)/PUT/DELETE を模擬

## 9. v0.3: `cf-publish worker deploy`（2026-08-27 着手）

weather からの要望。アメダス 10 分値の収集 Worker（10 分ごとに気象庁から取り、
加工せず R2 へ置く）を wrangler なしで配備したい、が発端。Pages と R2 は
cf-publish で足りていて、Worker だけが wrangler かダッシュボード貼り付けに
残っていた。種は `examples/form-worker/deploy.py`（Worker + D1 を REST API 直叩きで
配備する実運用コード）で、multipart の作法はそこで解けている。

- **API は公開されているもの**（Pages の資産 API と違い半公式ではない）:
  `PUT /accounts/{id}/workers/scripts/{name}`（multipart。metadata 1 パート＋
  モジュール 1 パート）、`PUT .../schedules`（cron）、R2 バケットの GET/POST
- **認証**: `CLOUDFLARE_API_TOKEN` に **Workers Scripts: Edit** が要る
  （Pages トークンには無い）。バケット作成には Workers R2 Storage: Edit も。
  401/403 はその旨を書いたエラーにする
- **`wrangler.toml` を既定値として読む**（発注者判断）。フラグだけにすると
  weather 側が toml と CLI の二重管理になるため。フラグが優先、r2/vars は
  バインディング名で併合、`--cron` を渡したときは toml の cron を置き換える。
  `[env.*]` は無視
  - 読み手は `tomllib`（3.11+）→ `tomli` → 内蔵の簡易リーダー、の順。CI は
    3.9 から回すので簡易リーダーが要る。**読めない書き方は推測せず PagesError**
    （設定の黙った誤読は、間違ったバインディングでのデプロイになる）
  - 簡易リーダーは tomllib と同じ結果になることを test で突き合わせる
- **シークレット**: `--secret 名前` は同名の環境変数から読み、値は出力しない。
  アップロードはバインディング一覧を丸ごと置き換えるので、`keep_bindings:
  ["secret_text"]` を常に付ける（付けないと再デプロイのたびにシークレットが
  黙って消える。ここだけが半公式のフィールド）
- **workers.dev は既定で触らない**。`--workers-dev` / `--no-workers-dev` を
  指定したときだけ変更する（weather の収集 Worker は公開エンドポイントに
  してはいけない — 無料枠 10 万リクエスト/日を訪問者が食い潰すため）
- **バンドラーは持たない**。ディレクトリ内の .js/.mjs/.json/.wasm/.txt を
  モジュールとしてそのまま上げる（相対 import は動く、npm は不可）。
  `node_modules` は既定で除外、合計 10MiB で事前に止める
- **対象外**: KV・D1・キュー・サービスバインディング（必要になってから）、
  ルート/カスタムドメインの割当、`wrangler.jsonc`
- テスト（Workers）: MockTransport で受信バイト列から multipart を自前で分解し、
  「スクリプトのパート名 = main_module」「ファイルパートであること」
  「Content-Type が application/javascript+module」を検査する
  （httpx を信じたモックでは、この作法の崩れを検知できない）

## 10. v0.4: R2 の照合（2026-08-28、officework の要望）

officework から来た要望は1つだけだった。「**上げたことになっているが中身が
違う**、が配布でいちばん怖い形なので、上げた後にハッシュを照合して合わなければ
失敗させてほしい」。理由も具体的で、向こうの release.yml は「署名なしの物が
混ざっていたら下書きに落とす」見張りを持っている（2026-08-17 に署名なしを
「署名つき」と説明して公開しかけた事故があったため）。

同じ回答で分かったこと: 配布物は GitHub Releases に置いていて R2 へ移す予定は
未定、実測で最大 100MB 見込み。**R2 のマルチパートは当面要らない**（ロードマップの
優先度を下げてよい）。1ファイル 5GB の上限には遠い。

- **常時の検算（追加リクエストなし）**: PUT に `Content-MD5` を付ける。壊れた
  本文はサーバーが 400 BadDigest で受け取らない。返る `ETag` はローカルの MD5 と
  照合する（単一 PUT の ETag は中身の MD5 ＝ 差分判定が既に依拠している事実）。
  **ETag が返らない応答も失敗**にする。「確かめられなかった」を成功と呼ばない
- **`--verify`（一覧を取り直す）**: 転送後にもう一度 ListObjectsV2 を回し、
  **飛ばした物も含めて全部**を照合する。飛ばす判断のもとになった一覧そのものが
  古いことがあるため。`--delete` 併用時は「消えていない物」も見つける。
  確認の根拠を「成功と言った当の応答」から「取り直した値」へ移すのが目的
- 不一致は1件ずつでなく**一覧で**報告する（1個だけ壊れたのか全部なのかで
  原因が違う）。先頭10件＋残数
- Pages 側には同じ手立てを入れない。内容アドレス方式で、ハッシュそのものを鍵に
  保存しているため（照合は構造として済んでいる）
- テスト（R2）: 偽サーバを**本物に寄せた**。PUT は ETag を返し、Content-MD5 を
  検算して合わなければ 400 を返す。加えて「**2回目の一覧から嘘をつく**」
  サーバを用意し、PUT は正しい ETag を返すのに読み直すと違う、という
  いちばん怖い形を再現している
