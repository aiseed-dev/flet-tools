# flet-tools

[Flet](https://flet.dev) のパッケージを置くリポジトリです。Flet の拡張と、Flet のアプリで使う部品を
置きます。どれも MIT で、パッケージごとに PyPI に出します。写して使う雛形と文書は
[recipes/](recipes/) にあります。

| パッケージ | 中身 | PyPI |
|---|---|---|
| [flet-gpumap](flet-gpumap/) | GPU で格子データ(気象の予報など)を地図に描く Flet の拡張 | (まだ出していない) |

## 雛形と文書(recipes/)

PyPI には出しません。使うアプリのリポジトリに写して、名前と道を合わせて使います。

| 雛形 | 中身 |
|---|---|
| [flet-windows-release](recipes/flet-windows-release/) | Flet のアプリの Windows 版を GitHub Actions で組み立て、git のタグの版で Release に載せる。重い import の間に先に出す起動の待ち画面も |

## この部品で作ったアプリ

- [AIseed Weather](https://weather.time-j.net/app/)([aiseed-dev/weather](https://github.com/aiseed-dev/weather)):
  Flet で作った、気象の予報を見るデスクトップアプリです。
  - 地図は、flet-gpumap の前身の flet-gpufield で描いています。flet-gpumap が PyPI に出たら、
    そちらに切り替える予定です。
  - recipes/flet-windows-release は、このアプリの Windows 版の配り方から作りました。

Flet の物でないパッケージ(cf-publish、nc4rs など)は [aiai-tools](https://github.com/aiseed-dev/aiai-tools)
の packages/ に置きます。会社や団体のためのスキルも aiai-tools、個人のための物は
[aiai](https://github.com/aiseed-dev/aiai) にあります。

## 公開

`<パッケージ>-v<版>` のタグ(たとえば `flet-gpumap-v0.1.0`)を push すると、
`.github/workflows/publish-<パッケージ>.yml` が、そのフォルダーを組んで PyPI に出します。タグの版と、
組んだ物の版が違うときは止まります。PyPI の側には、パッケージごとに、このリポジトリのワークフローを
Trusted Publishing として登録します。

## ライセンス

MIT([LICENSE](LICENSE))。recipes/ も同じです。
