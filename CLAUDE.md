# このリポジトリで作業するときの決まり

flet-tools は、Flet のパッケージを置くリポジトリです(Flet の拡張と、Flet のアプリで使う部品)。Flet の
物でないパッケージは、ここには置かず、aiai-tools(aiseed-dev/aiai-tools の packages/)に置きます
(2026-10-18 に発注者が決めた)。新しいパッケージの相談が来て Flet の物でなければ、aiai-tools の
セッションに回します。会社や団体のためのスキルも aiai-tools に置きます(2026-10-16 に発注者が決めた)。
書き方と作業の進め方は aiai-tools の CLAUDE.md と同じで、ここには違う所だけを書きます。

- パッケージは、一番上のフォルダーに 1 つずつ置く。どれも MIT
- パッケージでない、写して使う雛形と文書は `recipes/<名前>/` に置く(2026-10-18 に発注者が決めた)。
  PyPI には出さない。これも MIT。試験は標準ライブラリの unittest で、そのフォルダーの中で動かす
- 公開はパッケージごと。タグは `<パッケージ>-v<版>`、ワークフローは `.github/workflows/publish-<パッケージ>.yml`
- 版を上げたら、そのパッケージの CHANGELOG.md(あれば)を直す
- 試験は、パッケージのフォルダーの中で動かす
- ダウンロード(pip、conda、cargo、npm)は、名前、出どころ、大きさを伝えて許しを得てからにする
- push、PyPI の登録、タグの push は発注者がする。コミットまでで止める。コミットは触ったファイルだけを
  名前で指定する
- 秘密の値(PyPI のトークンなど)は、依頼にもリポジトリにも入れない

## 移した元(2026-10-16)

- flet-gpumap: aiseed-dev/aiai-tools の packages/(fe64259)

どれも履歴は写していない。前のリポジトリは、移った先を README に書いてからアーカイブにする(発注者がする)。
PyPI の Trusted Publishing は、このリポジトリに登録し直す。

cf-publish(aiseed-dev/cf-publish の 1cf9111)と nc4rs(aiai-tools の packages/ の fe64259)も一度ここに
移したが、Flet の物ではないので、2026-10-18 に発注者の指示で aiai-tools に返した(aiai-tools のセッションが
引き取る)。ここには残さない。

flet-printing は、2026-10-18 に発注者の指示で、aiseed-dev/flet-printing(ff15e40)の履歴ごと取り込んだ
(6 つのコミットを flet-printing/ の下に移して merge。タグ v0.2.0 は取り込んでいない。GitHub の元には残る)。
手元の ~/dev/flet-printing は消した。これからは、ここだけで直す。

## 公開の様子(2026-11-08 時点)

- flet-gpumap 0.1.0 を PyPI に出した(2026-11-08、タグ flet-gpumap-v0.1.0 で publish-flet-gpumap.yml が
  出した)。Trusted Publishing は発注者が登録した。GitHub の environment `pypi` は、最初の実行で GitHub が作った
  知らせた先: 「Weather アプリ開発」(2026-11-08)。まだ知らせていない(その日は動いていなかった): 「aiaiの管理者」
  (aiai の紹介ページにパッケージの節を足す)、aiai-tools のセッション(packages/flet-gpumap と
  publish-flet-gpumap.yml を消す)
- flet-printing 0.3.0(Flet 1.1)を PyPI に出した(2026-11-08、タグ flet-printing-v0.3.0)。PdfPreview の
  画面は発注者が見て確かめた。Publishing には前のリポジトリの登録(aiseed-dev/flet-printing、publish.yml)が
  まだ残っている。前のリポジトリをアーカイブにするときに消す(発注者)
- 動いたら、GitHub の aiseed-dev/flet-printing の README に移った先を書いてアーカイブにする(発注者)

weather(「Weather アプリ開発」のセッション)からの部品(2026-10-18 に相談して決めた):

- Windows 版の配り方と起動の待ち画面は、recipes/flet-windows-release に入れた。weather の AGPL の物を、
  著作者の発注者が MIT で出すと決めた。weather 側は写しのままで、元の雛形の場所を一行書く
- 時系列のグラフ(canvas_timeseries)は、weather 側で切り離してから、パッケージとしてここに入れる。
  発注者の指示を待つ
- 利用台数の記録(usage_report)は kaiseki とセットなので、ここには入れない(weather に置いたまま)
- README の「この部品で作ったアプリ」に AIseed Weather を載せた。weather の main は今 flet-gpufield を使っている。
  flet-gpumap に切り替えたら、README の書き方を直す

パッケージごとの覚え書き:

- flet-gpumap: weather の flet-gpufield から改名(Python と Dart のパッケージ名、シェーダーの道)。部品の名前
  GpuField はそのまま。weather の動く地図で、Linux と Web の組み立てと Web での表示を確かめた(2026-10-14)
- flet-printing: PyPI の 0.2.0(Flet 0.85 用)。0.3.0 で Flet 1.1 に合わせた。使っている所: officework の sample/flet_insatsu、pykobo の README
