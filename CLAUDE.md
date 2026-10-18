# このリポジトリで作業するときの決まり

flet-tools は、Python のパッケージを置くリポジトリです。中心は Flet の拡張です。会社や団体のための
スキルは aiai-tools に置き、ここには置きません(2026-10-16 に発注者が決めた)。書き方と作業の進め方は
aiai-tools の CLAUDE.md と同じで、ここには違う所だけを書きます。

- パッケージは、一番上のフォルダーに 1 つずつ置く。どれも MIT
- パッケージでない、写して使う雛形と文書は `recipes/<名前>/` に置く(2026-10-18 に発注者が決めた)。
  PyPI には出さない。これも MIT。試験は標準ライブラリの unittest で、そのフォルダーの中で動かす
- 公開はパッケージごと。タグは `<パッケージ>-v<版>`、ワークフローは `.github/workflows/publish-<パッケージ>.yml`
- 版を上げたら、そのパッケージの CHANGELOG.md(あれば)を直す
- 試験は、パッケージのフォルダーの中で動かす。比べる相手がある物は、相手と比べる(nc4rs は netCDF4)
- ダウンロード(pip、conda、cargo、npm)は、名前、出どころ、大きさを伝えて許しを得てからにする
- push、PyPI の登録、タグの push は発注者がする。コミットまでで止める。コミットは触ったファイルだけを
  名前で指定する
- 秘密の値(PyPI のトークン、Cloudflare の API トークンなど)は、依頼にもリポジトリにも入れない

## 移した元(2026-10-16)

- flet-printing: aiseed-dev/flet-printing の ff15e40
- cf-publish: aiseed-dev/cf-publish の 1cf9111
- flet-gpumap、nc4rs: aiseed-dev/aiai-tools の packages/(fe64259)

どれも履歴は写していない。前のリポジトリは、移った先を README に書いてからアーカイブにする(発注者がする)。
PyPI の Trusted Publishing は、このリポジトリに登録し直す。

## 残っていること(2026-10-18 時点。aiai-tools のセッションからの引き継ぎ)

公開までの順番。どれも発注者がする所は発注者がする。

1. GitHub に aiseed-dev/flet-tools を作り(発注者が作成中)、`git push -u origin main`(remote は付けてある)
2. GitHub の flet-tools に environment `pypi` を作る
3. pypi.org で、4 つとも Trusted Publishing を登録する(リポジトリ aiseed-dev/flet-tools、ワークフロー
   `publish-<パッケージ>.yml`、environment `pypi`)。flet-printing と cf-publish は前のリポジトリからの付け替え、
   flet-gpumap と nc4rs は新しい pending publisher
4. タグで出す: `flet-gpumap-v0.1.0`、`nc4rs-v0.1.0`。flet-printing と cf-publish は、次の版を出すときから
   ここのタグ(`flet-printing-v…`、`cf-publish-v…`)を使う
5. 出たら知らせる: 「Weather アプリ開発」のセッション(weather の ローカルのブランチ prep/flet-gpumap が
   flet-gpumap==0.1.0 を待っている。nc4rs への切り替えも PyPI の後)、「aiaiの管理者」(aiai の紹介ページに
   パッケージの節を足す)、aiai-tools のセッション(aiai-tools の packages/ と publish-flet-gpumap.yml、
   publish-nc4rs.yml を消す)
6. 動いたら、aiseed-dev/flet-printing と aiseed-dev/cf-publish の README に移った先を書いてアーカイブにする
   (発注者)。cf-publish の conda-forge のレシピ(別のセッションで PR を出している)の URL も直す

weather(「Weather アプリ開発」のセッション)からの部品(2026-10-18 に相談して決めた):

- Windows 版の配り方と起動の待ち画面は、recipes/flet-windows-release に入れた。weather の AGPL の物を、
  著作者の発注者が MIT で出すと決めた。weather 側は写しのままで、元の雛形の場所を一行書く
- 時系列のグラフ(canvas_timeseries)は、weather 側で切り離してから、パッケージとしてここに入れる。
  発注者の指示を待つ
- 利用台数の記録(usage_report)は kaiseki とセットなので、ここには入れない(weather に置いたまま)
- README の「この部品で作ったアプリ」に AIseed Weather を載せた。weather の main は今 flet-gpufield を使っている。
  flet-gpumap と nc4rs に切り替えたら、README の書き方を直す

パッケージごとの覚え書き:

- flet-gpumap: weather の flet-gpufield から改名(Python と Dart のパッケージ名、シェーダーの道)。部品の名前
  GpuField はそのまま。weather の動く地図で、Linux と Web の組み立てと Web での表示を確かめた(2026-10-14)
- nc4rs: 組むのは maturin(pyo3 0.29、abi3-py310)。`maturin build --release` で wheel ができる。試験は
  `python -m unittest discover -s tests` で netCDF4 と xarray が要る(netCDF4 1.7.4 と比べて、決まった形と
  無作為 60 件ずつが一致)。速さは README のとおり(Python から読み 1.1〜2.4 倍、書き 2.3〜2.4 倍)。
  `vendor/` の hdf5-writer と hdf5-reader の速くする直しは、上流(roteiro-gis/netcdf-rust)へのプルリクエストを
  発注者の確認待ち。上流に入ったら vendor/ を消す。zstd の圧縮、追記("a")、グループはまだ無い。
  `publish-nc4rs.yml` は GitHub の上でまだ動かしていない(macOS の Intel は macos-15-intel にした。
  macos-13 は今の runner の一覧に無い、2026-10-18 に確かめた)
- cf-publish: PyPI の 0.3.1。試験は `pip install -e .[dev]` と pytest(ここでは動かしていない)
- flet-printing: PyPI の 0.2.0
