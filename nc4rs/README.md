# nc4rs

NetCDF-4 と classic のファイルを、C を使わずに読み書きする Python のパッケージです。netCDF4 に近い
使い方(`Dataset`、`createDimension`、`createVariable`、スライスでの読み書き、scale・offset・欠測の
自動の処理)と、xarray からの読み込み(`engine="nc4rs"`)と書き出し(`nc4rs.to_netcdf`)ができます。

中身は [netcdf-rust](https://github.com/roteiro-gis/netcdf-rust)(Rust の NetCDF と HDF5、
MIT OR Apache-2.0、0.9.1)を PyO3 でつないだ物です。libnetcdf も libhdf5 も要りません。チャンクの
圧縮と展開は並列で、圧縮は速い deflate(zlib-rs)です。

```python
import nc4rs

with nc4rs.Dataset("t.nc", "w") as ds:
    ds.createDimension("time", None)
    ds.createDimension("x", 3)
    v = ds.createVariable("t", "i2", ("time", "x"), zlib=True, fill_value=-32767)
    v.scale_factor = 0.01
    v[0] = [1.5, 2.25, 3.0]

with nc4rs.Dataset("t.nc") as ds:
    print(ds["t"][:])          # 1 つずつ
    print(ds.read_many())       # 全部の変数を並列に

import xarray as xr
ds = xr.open_dataset("t.nc", engine="nc4rs")
nc4rs.to_netcdf(ds, "out.nc", encoding={"t": {"zlib": True}})
```

## 速さ(2026-10-14、24 コアの PC、Python から)

ECMWF Open Data の 0.25° 全球 1 ステップ(int16、shuffle、deflate 4)で、netCDF4 1.7.4(libnetcdf)と
比べました。結果は、値、欠測、型まで netCDF4 と同じです。nc4rs で書いたファイルを netCDF4 で読むと、
netCDF4 で書いた物と同じになります。

| | 地上(36 変数、36MB) | 気圧面(10 変数 × 14 面、148MB) |
|---|---|---|
| 読み、変数を 1 つずつ(scale と欠測を含む) | 1.4 倍 | 1.5 倍 |
| 読み、`read_many` | 2.4 倍 | 1.5 倍 |
| xarray の `load()` | 1.1 倍 | 1.4 倍 |
| xarray からの書き出し | 2.4 倍 | 2.3 倍 |

Rust だけで測ると、書きは 6.6〜10.9 倍、読みは 5.5〜6.7 倍です。Python からでは、scale と欠測の
処理(numpy)と xarray の符号化が、ほかの時間の多くを占めます。

## できないこと(0.1.0)

- 圧縮は zlib(deflate)だけです。zstd と szip はまだありません
- あるファイルへの追記(`"a"`)はできません。ファイルはメモリーの中で作り、閉じたときに書きます
- グループ、ユーザー定義の型(compound、enum、vlen)は読み書きできません
- 書いている途中のファイルは読めません

値には関わらない、libnetcdf との違いもあります。

- チャンクを指定しないときの大きさが違います(たとえば 721 × 1440 の面を、libnetcdf は 1 つ、
  nc4rs は 2 つのチャンクにします)
- `_NCProperties` を書かないので、`ncdump -hs` では `_IsNetcdf4 = 0` と出ます。netCDF4 と xarray では
  ふつうに読めます。ほかの道具(netCDF-Java など)での扱いは確かめていません

## 試験

```
python -m unittest discover -s tests
```

netCDF4 と xarray が要ります。netCDF4 で書いて nc4rs で読む、nc4rs で書いて netCDF4 で読む、を、
決まった形と、無作為な形・型・チャンク・圧縮・欠測(60 件ずつ)で比べます。

## 公開

`nc4rs-v0.1.0` のようなタグを push すると、GitHub Actions(`.github/workflows/publish-nc4rs.yml`)が
Linux、macOS、Windows の wheel を作り、PyPI に出します。

## ライセンス

MIT([LICENSE](LICENSE))。`vendor/` の hdf5-writer と hdf5-reader は netcdf-rust の物で、
MIT OR Apache-2.0 です([vendor/README.md](vendor/README.md))。
