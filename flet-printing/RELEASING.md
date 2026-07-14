# リリース手順（PyPIへの公開）

公開は**タグの push だけ**で完了する。GitHub Actions
（`.github/workflows/publish.yml`）が Trusted Publishing（OIDC）で
PyPI にアップロードする。

## 手順

```bash
# 1. バージョンを上げる ── 定義箇所はここだけ
#    （pyproject.toml は dynamic version）
vi src/flet_printing/__init__.py    # __version__ = "X.Y.Z"
#    Dart側の表示用バージョンも合わせる（cosmetic）
vi src/flutter/flet_printing/pubspec.yaml   # version: X.Y.Z

# 2. CHANGELOG.md に節を書く

# 3. 検証
cd src/flutter/flet_printing && flutter analyze && cd ../../..
python -m build --wheel && unzip -l dist/*.whl | grep flutter/   # flutter/同梱の確認
# flet buildの一気通貫検証が要るとき（Flet新版追従時など）は、使い捨ての
# 検証アプリを作る ── READMEのUsageコードがそのまま完全なアプリ:
#   flet create /tmp/fp_check && cd /tmp/fp_check
#   （src/main.py にREADMEのUsageを貼り、pyproject.tomlに追記:
#     dependencies に "flet-printing"、
#     [tool.flet.dev_packages] flet-printing = "/home/dev/dev/flet-printing"）
#   flet build linux --yes && ./build/linux/fp_check

# 4. コミットして push
git add -A && git commit -m "vX.Y.Z" && git push origin main

# 5. タグを打って push（公開トリガー）
git tag vX.Y.Z && git push origin vX.Y.Z
```

## 初回のみ（Trusted Publisher登録）

<https://pypi.org/manage/account/publishing/> の
「Add a new pending publisher」で:

- PyPI Project Name: `flet-printing`
- Owner: `aiseed-dev` / Repository: `flet-printing`
- Workflow: `publish.yml` / Environment: `pypi`

## 注意

- wheelに `flutter/` ディレクトリが同梱されていることがこのパッケージの
  生命線（flet buildはpipで入ったパッケージ内のFlutterコードを参照する）。
  タグ前に `python -m build --wheel && unzip -l dist/*.whl | grep flutter/`
  で確認する。
- Fletの新バージョン（0.86等）が出たら、Dart側 `flet: ^0.85.3` の
  追従バンプが必要（pubの<1.0キャレットはマイナー固定のため）。
- PyPI公開はユーザー自身が行う（Claudeはpushしない）。
