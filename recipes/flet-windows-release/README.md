# flet-windows-release

Flet のアプリの Windows 版を、GitHub Actions で組み立てて配るための雛形です。パッケージではないので、
使うアプリのリポジトリに写して、名前と道を合わせて使います。MIT です。

[AIseed Weather](https://github.com/aiseed-dev/weather) の配り方から作りました。そちらでは、2026-10-18 に
`app-v0.1.1` のタグで実際に動かしました。出来た exe の ProductVersion と、アプリの中に出る版が、どちらも
0.1.1 になることを確かめています(Flet 1.0.4)。

| ファイル | 写す先 | すること |
|---|---|---|
| [windows-app.yml](windows-app.yml) | `.github/workflows/` | 組み立て、成果物に残す。タグなら Release にも載せる |
| [write_build_version.py](write_build_version.py) | `tools/` | git のタグから版を決めて書く(標準ライブラリだけ) |
| [boot.py](boot.py) | `[tool.flet.app] path` の `main.py` | 重い import の間に、先に「起動しています」を出す |

## 流れ

- タグでない push では、組み立てて成果物(artifact)に 14 日残すだけです。
- `app-vX.Y.Z` のタグを push すると、次のことをします。
  1. `write_build_version.py` が `X.Y.Z` を `_build_version.py` に書き、`BUILD_VERSION` を次の手順に渡す
  2. `flet build windows --build-version X.Y.Z` で組み立てる(exe の版もこれになる)
  3. 7z で zip にまとめ、`gh release create --prerelease` で Release に載せる
- 形の違うタグ(`app-v0.1`、`app-v1.0.0-rc1` など)は、最初の手順で止めます。

版を決めるのは git のタグだけです。リポジトリの中のどこにも、版を書き込んでおきません。

## 写した後に合わせる所

1. `windows-app.yml` で「直す」と書いた所を合わせる。合わせるのは、`APP_DIR`、`APP_NAME`、
   `VERSION_FILE`、`FLET_VERSION`、Python の版、入れる部品と試験、Release の説明。
2. `VERSION_FILE`(例: `src/myapp/_build_version.py`)を `.gitignore` に入れる。
3. アプリの `__init__.py` で版を読む。手元で動かすときはファイルが無いので、そのときの値も決めておく。

   ```python
   try:
       from myapp._build_version import __version__
   except ImportError:
       __version__ = "0.0.0.dev0"
   ```

4. アプリの本体が hatch で組まれる場合は、`pyproject.toml` に次を足す(下の「落とし穴」を見てください)。

   ```toml
   [tool.hatch.build.targets.wheel]
   artifacts = ["src/myapp/_build_version.py"]
   ```

5. `[tool.flet.windows] artifact` を `APP_NAME` と同じにする。Release の説明に、exe の名前として出るためです。
6. 待ち画面を使うなら、`boot.py` の `APP_MODULE` と `TITLE` を直して、`[tool.flet.app] path` の
   `main.py` として置く。本体のモジュールには、次の 2 つを用意します。
   - `App`: `page.render` に渡す部品
   - `configure(page)`(無くてもよい): 窓の大きさなどを整える関数

## 起動の待ち画面

本体の import が重いアプリ(xarray、matplotlib、cartopy など)では、Windows の配布版の初回の起動に
40 秒ほどかかることがあります。その間、Flutter の側は Python を待ちきれず、画面が白いままになります。

`boot.py` は、次の順で動きます。

1. 先に `page.add` で「起動しています」を出す。
2. 本体を `asyncio.to_thread(importlib.import_module, …)` で、別のスレッドで読み込む。
3. 読み終えたら、`page.render(App)` で画面を入れ替える。

読み込みに失敗したときは、白い画面のままにせず、何が起きたかを画面に出します。開発のとき
(`flet run`)は、今までどおり本体を直接走らせて構いません。

## 落とし穴

- **.gitignore のファイルは wheel に入らない。** hatch は、`.gitignore` に入っているファイルを wheel に
  入れません。`flet build` は、`dev_packages` や依存に書いたパッケージを、一度 wheel にしてから入れます。
  そのため、本体を wheel 経由で入れるアプリでは、タグから書いた `_build_version.py` が組み立てた物から
  落ちます。`artifacts` に書いて、wheel に入るようにしてください(上の 4)。
- **Release を作る権限。** `permissions: contents: write` が要ります。雛形には書いてあります。

## 試験

`write_build_version.py` の試験は、このフォルダーの中で、標準ライブラリだけで動きます。

```bash
python -m unittest discover -s tests
```

ワークフローと `boot.py` は、AIseed Weather の中で動かして確かめた物を、名前と道だけ外に出した物です。
雛形としては、まだ単独で動かしていません。
