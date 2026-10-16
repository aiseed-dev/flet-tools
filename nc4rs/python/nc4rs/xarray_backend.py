# SPDX-License-Identifier: MIT
"""xarray with nc4rs: xr.open_dataset(path, engine="nc4rs") and nc4rs.to_netcdf(ds, path).

Reading goes through xarray's own CF decoding (scale, offset, missing values,
times), so the result is the same as with engine="netcdf4". Values are read
when they are used.
"""
import numpy as np
import xarray as xr
from xarray.backends import BackendArray, BackendEntrypoint
from xarray.backends.common import AbstractDataStore
from xarray.backends.store import StoreBackendEntrypoint
from xarray.core import indexing

import nc4rs


class Nc4rsArray(BackendArray):
    def __init__(self, store, var):
        self.store = store
        self.var = var
        self.shape = var.shape
        self.dtype = np.dtype(object) if var._kind == "str" else np.dtype(var._kind)

    def __getitem__(self, key):
        return indexing.explicit_indexing_adapter(
            key, self.shape, indexing.IndexingSupport.OUTER, self._raw)

    def _raw(self, key):
        full = all(isinstance(k, slice) and k == slice(None) for k in key)
        if full:
            data = self.store.whole(self.var.name)
            if data is not None:
                return data
        return np.asarray(self.var[key])


class Nc4rsStore(AbstractDataStore):
    def __init__(self, filename):
        self.ds = nc4rs.Dataset(filename)
        self._whole = None

    def whole(self, name):
        # The first whole read (as by .load()) reads every variable in parallel;
        # each is handed out once, so the memory is not held twice.
        if self._whole is None:
            names = [n for n, v in self.ds.variables.items() if v._kind != "str"]
            self._whole = self.ds.read_many(names)
        return self._whole.pop(name, None)

    def get_variables(self):
        out = {}
        for name, v in self.ds.variables.items():
            v.set_auto_maskandscale(False)
            encoding = {"dtype": v.dtype, "source": self.ds.filepath()}
            chunks = v.chunking()
            if chunks != "contiguous":
                encoding["chunksizes"] = tuple(chunks)
            data = indexing.LazilyIndexedArray(Nc4rsArray(self, v))
            out[name] = xr.Variable(v.dimensions, data, dict(v._attrs), encoding)
        return out

    def get_attrs(self):
        return dict(self.ds._attrs)

    def get_dimensions(self):
        return {k: len(d) for k, d in self.ds.dimensions.items()}

    def get_encoding(self):
        unlimited = {k for k, d in self.ds.dimensions.items() if d.isunlimited()}
        return {"unlimited_dims": unlimited} if unlimited else {}

    def close(self):
        self.ds.close()


class Nc4rsBackendEntrypoint(BackendEntrypoint):
    description = "Read NetCDF-4 and classic files with nc4rs (netcdf-rust, no C)"
    url = "https://github.com/aiseed-dev/flet-tools/tree/main/nc4rs"
    open_dataset_parameters = ["filename_or_obj", "drop_variables", "mask_and_scale",
                               "decode_times", "concat_characters", "decode_coords",
                               "use_cftime", "decode_timedelta"]

    def open_dataset(self, filename_or_obj, *, drop_variables=None, mask_and_scale=True,
                     decode_times=True, concat_characters=True, decode_coords=True,
                     use_cftime=None, decode_timedelta=None):
        store = Nc4rsStore(str(filename_or_obj))
        return StoreBackendEntrypoint().open_dataset(
            store, mask_and_scale=mask_and_scale, decode_times=decode_times,
            concat_characters=concat_characters, decode_coords=decode_coords,
            drop_variables=drop_variables, use_cftime=use_cftime,
            decode_timedelta=decode_timedelta)

    def guess_can_open(self, filename_or_obj):
        name = str(filename_or_obj)
        return name.endswith((".nc", ".nc4", ".cdf"))


_ENCODING_KEYS = ("zlib", "complevel", "shuffle", "chunksizes", "compression")


def to_netcdf(ds, path, encoding=None, unlimited_dims=None, format="NETCDF4"):
    """Write an xarray Dataset with nc4rs, using xarray's CF encoding.

    encoding is per variable, as for Dataset.to_netcdf: dtype, scale_factor,
    add_offset, _FillValue, units, zlib, complevel, shuffle, chunksizes.
    """
    from xarray.conventions import cf_encoder, encode_dataset_coordinates

    encoding = encoding or {}
    if unlimited_dims is None:
        unlimited_dims = ds.encoding.get("unlimited_dims", set())
    # As xarray's own writers do: first the "coordinates" attributes, so that
    # scalar coordinates (time, step, a level) stay coordinates when read back
    variables, attrs = encode_dataset_coordinates(ds)
    for name, var in variables.items():
        var = var.copy(deep=False)
        var.encoding = {**var.encoding, **encoding.get(name, {})}
        variables[name] = var
    variables, attrs = cf_encoder(variables, dict(attrs))
    with nc4rs.Dataset(path, "w", format=format) as out:
        for k, v in attrs.items():
            out.setncattr(k, v)
        sizes = dict(ds.sizes)
        for d, n in sizes.items():
            out.createDimension(d, None if d in unlimited_dims else n)
        for name, var in variables.items():
            enc = var.encoding
            attrs = dict(var.attrs)
            fill = attrs.pop("_FillValue", None)
            data = np.asarray(var.values)
            dtype = str if data.dtype.kind in "OU" else data.dtype
            v = out.createVariable(
                name, dtype, var.dims, zlib=bool(enc.get("zlib") or enc.get("compression") == "zlib"),
                complevel=enc.get("complevel", 4), shuffle=enc.get("shuffle", True),
                chunksizes=enc.get("chunksizes"), fill_value=fill)
            v.set_auto_maskandscale(False)
            for k, a in attrs.items():
                v.setncattr(k, a)
            v[...] = data
