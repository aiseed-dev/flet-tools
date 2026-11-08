# リリース手順（PyPIへの公開）

公開は**タグの push だけ**で完了する。flet-tools の GitHub Actions
（リポジトリの一番上の `.github/workflows/publish-flet-printing.yml`）が
Trusted Publishing（OIDC）で PyPI にアップロードする。タグの版と組んだ wheel の版が
違うときは止まる。

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
#     [tool.flet.dev_packages] flet-printing = "/home/dev/dev/flet-tools/flet-printing"）
#   flet build linux --yes && ./build/linux/fp_check

# 4. コミットして push（触ったファイルだけを名前で指定する）
git add src/flet_printing/__init__.py src/flutter/flet_printing/pubspec.yaml CHANGELOG.md
git commit -m "flet-printing X.Y.Z" && git push origin main

# 5. タグを打って push（公開トリガー。v0.2.0 までは元の aiseed-dev/flet-printing の v* タグ）
git tag flet-printing-vX.Y.Z && git push origin flet-printing-vX.Y.Z
```

## 初回のみ（Trusted Publisher登録）

<https://pypi.org/manage/account/publishing/> の
プロジェクト flet-printing の Publishing で、GitHub の publisher を足す
（0.2.0 までは aiseed-dev/flet-printing の publish.yml から出していた）:

- Owner: `aiseed-dev` / Repository: `flet-tools`
- Workflow: `publish-flet-printing.yml` / Environment: `pypi`

## 注意

- wheelに `flutter/` ディレクトリが同梱されていることがこのパッケージの
  生命線（flet buildはpipで入ったパッケージ内のFlutterコードを参照する）。
  タグ前に `python -m build --wheel && unzip -l dist/*.whl | grep flutter/`
  で確認する。
- Dart側は `flet: ^1.1.0`（1.x の間は追従のバンプは要らない）。Flet 1.1 から
  Material は `material_ui` に移った。`printing` の PdfPreview は SDK の Material で
  書かれているので、`pdf_preview_control.dart` が SDK の Theme・Material・訳を足して
  包んでいる。printing が material_ui に移ったら、その包みを外す。
- PyPI公開はユーザー自身が行う（Claudeはpushしない）。
