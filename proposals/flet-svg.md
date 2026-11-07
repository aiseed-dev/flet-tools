# 提案: flet-svg（字も描く SVG の部品）と flet-chart（グラフの部品）

書いた日: 2026-11-07。出どころ: seed（aiseed-dev/seed）の天気の画面。

## 何が困ったか

seed の天気の画面は、純 Python で SVG を組んだグラフ（`src/seed/chart.py`。~/dev/weather の
`weatherlib/svgchart.py` と同じ作り）を `ft.Image(src=<svg bytes>)` で出す。Flet 1.1 の Image は
SVG を flutter_svg で描くが、flutter_svg は `<text>` を描かない。軸の数、日付、凡例が全部消える。
今は resvg-py で PNG にして出している（PC では動く。Android の wheel が無く、スマートフォンでは字が出ない）。

## 二つの道

### 1. flet-svg

Flutter の `jovial_svg`（`<text>` を描く。pub.dev）を Flet の拡張として包む。

```python
from flet_svg import Svg
Svg(src=svg_text_or_bytes, width=960, height=240)   # そのまま描く。width は自然な大きさでよい
```

- Python 側は `src/flet_svg/svg.py` の一つ（`ft.Control` を継承、`src` を渡すだけ）。
- Flutter 側は `src/flutter/flet_svg/`（pubspec に `jovial_svg`、lib に一つの widget）。
- 型は flet-printing をそのまま写す（フォルダーの形、pyproject、publish の workflow、CHANGELOG）。
- 試験: seed の `chart.py` が作る四つの SVG（一時間ごと、日ごと、作業の目安、土）を描いて、字が出る事。

これが一番小さい。seed の側は `ft.Image` を `Svg` に替えるだけで、resvg の回り道を外せる。

### 2. flet-chart

Flutter の `fl_chart` を包み、線と棒のグラフを部品にする。触ると値が出る、幅に合わせて描き直す。

```python
from flet_chart import LineBarChart, Series
LineBarChart(x=["11/8", "11/9", ...], lines=[Series("最高", tmax, "#F92500"), Series("最低", tmin, "#0C00CC")],
             bars=[Series("降水", rain, "#1987E5")], right_axis="mm", left_axis="℃")
```

- 大きいが、グラフを使うアプリ（weather、seed）の両方で使える。SVG を経ないので字の問題が無い。
- 色と見た目は weatherlib/svgchart.py の決まり（最高 #F92500、平均 #008000、最低 #0C00CC、降水 #1987E5）を既定にする。

## 順

1 を先に作る（一日の大きさ）。seed の提出（11-08）の後。2 は weather のアプリで要る時に。

## 置き場

このリポジトリに `flet-svg/`（と後で `flet-chart/`）。MIT。タグ `flet-svg-v0.1.0` で PyPI へ。
