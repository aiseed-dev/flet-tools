# vendor

netcdf-rust(https://github.com/roteiro-gis/netcdf-rust)の hdf5-writer と hdf5-reader の 0.9.1 に、
速くする直しを加えた物です。ライセンスは元のとおり MIT OR Apache-2.0 です
([LICENSE-MIT](LICENSE-MIT)、[LICENSE-APACHE](LICENSE-APACHE))。

- hdf5-writer: データセットごと、チャンクごとの圧縮を rayon で並列にし、deflate を zlib-rs にしました
- hdf5-reader: 2 バイトと 4 バイトの要素の unshuffle を特化し、余分な写しをやめました

元の crate の試験とベンチマークのファイルは入れていません(Cargo.toml からも外しています)。
直しは上流に提案する予定です。上流に入ったら、ここは消して crates.io の物を使います。
