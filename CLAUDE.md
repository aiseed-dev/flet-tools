# このリポジトリで作業するときの決まり

flet-tools は、Python のパッケージを置くリポジトリです。中心は Flet の拡張です。会社や団体のための
スキルは aiai-tools に置き、ここには置きません(2026-10-16 に発注者が決めた)。書き方と作業の進め方は
aiai-tools の CLAUDE.md と同じで、ここには違う所だけを書きます。

- パッケージは、一番上のフォルダーに 1 つずつ置く。どれも MIT
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
