# SPDX-License-Identifier: MIT
"""Read and write NetCDF-4 and classic files without C, with a netCDF4-like API.

    import nc4rs
    with nc4rs.Dataset("t.nc", "w") as ds:
        ds.createDimension("x", 3)
        v = ds.createVariable("t", "i2", ("x",), zlib=True, fill_value=-32767)
        v.scale_factor = 0.01
        v[:] = [1.5, 2.25, 3.0]
    with nc4rs.Dataset("t.nc") as ds:
        print(ds["t"][:])

The files are read and written by netcdf-rust (no libnetcdf, no libhdf5). Chunks
are compressed and decompressed in parallel. A file is made in memory and
written when it is closed; adding to a file that exists ("a") is not supported.
"""
import numpy as np

from nc4rs._nc4rs import Reader, Writer, __version__

__all__ = ["Dataset", "Variable", "Dimension", "to_netcdf", "__version__"]

_KINDS = {np.dtype(k): k for k in ("i1", "u1", "i2", "u2", "i4", "u4", "i8", "u8", "f4", "f8")}
# The fill values of libnetcdf, used when a variable has no _FillValue
_DEFAULT_FILL = {
    "i1": -127, "u1": 255, "i2": -32767, "u2": 65535, "i4": -2147483647,
    "u4": 4294967295, "i8": -9223372036854775806, "u8": 18446744073709551614,
    "f4": 9.969209968386869e36, "f8": 9.969209968386869e36,
}


def _attr_in(kind, value):
    if kind == "str":
        return value
    if kind == "strs":
        return value[0] if len(value) == 1 else list(value)
    if isinstance(value, bytes):  # pyo3 gives unsigned bytes as bytes
        value = list(value)
    a = np.array(value, dtype=kind)
    return a[0] if a.size == 1 else a


def _attr_out(value):
    if isinstance(value, str):
        return "str", value
    if isinstance(value, (list, tuple)) and value and all(isinstance(x, str) for x in value):
        return "strs", list(value)
    a = np.atleast_1d(np.asarray(value))
    if a.dtype == np.bool_:
        a = a.astype("i1")
    if a.dtype.kind in "iu" and a.dtype not in _KINDS:
        a = a.astype("i8")
    kind = _KINDS.get(a.dtype.newbyteorder("=")) or ("f8" if a.dtype.kind == "f" else "i8")
    return kind, a.astype(kind).tolist()


def _slices(key, shape):
    """Turn an index into Rust slices, the shape to read back, and what numpy still has to do."""
    if not isinstance(key, tuple):
        key = (key,)
    if any(k is Ellipsis for k in key):
        i = next(n for n, k in enumerate(key) if k is Ellipsis)
        key = key[:i] + (slice(None),) * (len(shape) - len(key) + 1) + key[i + 1:]
    key = key + (slice(None),) * (len(shape) - len(key))
    if len(key) > len(shape):
        raise IndexError("too many indices")
    sel, after = [], []
    for k, n in zip(key, shape):
        if isinstance(k, (int, np.integer)):
            k = int(k) + n if k < 0 else int(k)
            if not 0 <= k < n:
                raise IndexError(f"index {k} is out of range for size {n}")
            sel.append((k, k + 1, 1))
            after.append(0)
        elif isinstance(k, slice):
            start, stop, step = k.indices(n)
            if step < 0:
                lo = stop + 1 if stop >= -1 else 0
                sel.append((max(lo, 0), start + 1, 1))
                after.append(slice(None, None, step))
            else:
                sel.append((start, max(stop, start), step))
                after.append(slice(None))
        else:  # a list or array of indices, or a mask
            k = np.asarray(k)
            if k.dtype == np.bool_:
                k = np.nonzero(k)[0]
            k = np.where(k < 0, k + n, k)
            lo, hi = (int(k.min()), int(k.max()) + 1) if k.size else (0, 0)
            sel.append((lo, hi, 1))
            after.append(k - lo)
    return sel, tuple(after)


class Dimension:
    def __init__(self, name, size, unlimited):
        self.name = name
        self.size = size
        self._unlimited = unlimited

    def __len__(self):
        return self.size

    def isunlimited(self):
        return self._unlimited

    def __repr__(self):
        kind = "unlimited " if self._unlimited else ""
        return f"<nc4rs.Dimension {kind}{self.name!r}, size = {self.size}>"


class Variable:
    """A variable of a Dataset. Index it like netCDF4.Variable."""

    def __init__(self, ds, name, dimensions, shape, dtype, attrs):
        object.__setattr__(self, "_ds", ds)
        object.__setattr__(self, "name", name)
        object.__setattr__(self, "dimensions", tuple(dimensions))
        object.__setattr__(self, "_shape", tuple(int(n) for n in shape))
        object.__setattr__(self, "_kind", dtype)
        object.__setattr__(self, "_attrs", dict(attrs))
        object.__setattr__(self, "_mask", True)
        object.__setattr__(self, "_scale", True)
        object.__setattr__(self, "_always_mask", True)

    @property
    def dtype(self):
        return str if self._kind == "str" else np.dtype(self._kind)

    @property
    def shape(self):
        if self._ds._writer is not None:
            return tuple(len(self._ds.dimensions[d]) for d in self.dimensions)
        return self._shape

    @property
    def ndim(self):
        return len(self.dimensions)

    @property
    def size(self):
        return int(np.prod(self.shape))

    def __len__(self):
        return self.shape[0]

    # Attributes, as in netCDF4: v.units, v.setncattr("units", "K")
    def ncattrs(self):
        return list(self._attrs)

    def getncattr(self, name):
        return self._attrs[name]

    def setncattr(self, name, value):
        self._ds._need_writer()
        kind, out = _attr_out(value)
        self._ds._writer.add_attribute(self.name, name, kind, out)
        self._attrs[name] = value

    def __getattr__(self, name):
        try:
            return self._attrs[name]
        except KeyError:
            raise AttributeError(name) from None

    def __setattr__(self, name, value):
        if name.startswith("_") and name != "_FillValue":
            object.__setattr__(self, name, value)
        else:
            self.setncattr(name, value)

    def set_auto_maskandscale(self, flag):
        self._mask = self._scale = bool(flag)

    def set_auto_mask(self, flag):
        self._mask = bool(flag)

    def set_auto_scale(self, flag):
        self._scale = bool(flag)

    def set_always_mask(self, flag):
        self._always_mask = bool(flag)

    # Reading
    def __getitem__(self, key):
        if self._ds._reader is None:
            raise OSError("this file is open for writing; reading back is not supported")
        if self._kind == "str":
            data = np.array(self._ds._reader.read_strings(self.name), dtype=object).reshape(self._shape)
            return data[key]
        sel, after = _slices(key, self._shape)
        raw, shape = self._ds._reader.read(self.name, sel)
        dt = "S1" if self._kind == "S1" else self._kind
        data = np.frombuffer(raw, dtype=dt).reshape(shape)
        for axis, a in enumerate(after):
            if isinstance(a, np.ndarray):
                idx = [slice(None)] * data.ndim
                idx[axis] = a
                data = data[tuple(idx)]
        data = data[tuple(a if not isinstance(a, np.ndarray) else slice(None) for a in after)]
        return self._decode(data.copy())

    def _missing(self):
        vals = []
        for name in ("_FillValue", "missing_value"):
            if name in self._attrs:
                vals.extend(np.atleast_1d(self._attrs[name]).tolist())
        if "_FillValue" not in self._attrs and self._kind in _DEFAULT_FILL:
            vals.append(_DEFAULT_FILL[self._kind])
        return vals

    def _decode(self, data):
        if self._kind == "S1":
            return data
        mask = np.zeros(data.shape, dtype=bool)
        if self._mask:
            for m in self._missing():
                mask |= data == np.array(m).astype(data.dtype)
            lo = self._attrs.get("valid_min")
            hi = self._attrs.get("valid_max")
            if "valid_range" in self._attrs:
                lo, hi = self._attrs["valid_range"]
            if lo is not None:
                mask |= data < lo
            if hi is not None:
                mask |= data > hi
            if data.dtype.kind == "f":
                mask |= np.isnan(data)
        if self._scale and ("scale_factor" in self._attrs or "add_offset" in self._attrs):
            scale = self._attrs.get("scale_factor", 1.0)
            offset = self._attrs.get("add_offset", 0.0)
            out = np.result_type(np.asarray(scale), np.asarray(offset), np.float32)
            data = data.astype(out) * scale + offset
        if self._mask and (mask.any() or self._always_mask):
            fill = self._attrs.get("_FillValue", _DEFAULT_FILL.get(self._kind))
            if mask.any() and fill is not None:  # as netCDF4: the fill value under the mask
                data[mask] = np.array(fill).astype(data.dtype)
            return np.ma.masked_array(data, mask=mask, fill_value=fill)
        return data

    def _from_raw(self, raw, shape):
        dt = "S1" if self._kind == "S1" else self._kind
        return self._decode(np.frombuffer(raw, dtype=dt).reshape(shape).copy())

    # Writing
    def __setitem__(self, key, value):
        w = self._ds._need_writer()
        if self._kind == "str":
            w.write_strings(self.name, [str(x) for x in np.asarray(value, dtype=object).ravel()])
            return
        value = self._encode(value)
        dims = [self._ds.dimensions[d] for d in self.dimensions]
        big = 1 << 62
        sel, after = _slices(key, [big if d.isunlimited() else len(d) for d in dims])
        if any(isinstance(a, np.ndarray) or (isinstance(a, slice) and a != slice(None)) for a in after):
            raise IndexError("writing with reversed steps or index lists is not supported")
        # An open end on an unlimited axis takes its length from the value
        kept = [i for i, a in enumerate(after) if not isinstance(a, int)]
        pad = len(kept) - value.ndim
        for j, i in enumerate(kept):
            start, stop, step = sel[i]
            if stop >= big:
                n = value.shape[j - pad] if j >= pad else 1
                sel[i] = (start, start + (n - 1) * step + 1 if n else start, step)
        want = tuple(len(range(a, b, st)) for a, b, st in sel)
        value = np.broadcast_to(value, want) if value.shape != want else value
        for d, (a, b, st) in zip(dims, sel):
            if d.isunlimited() and b > a:
                d.size = max(d.size, a + (len(range(a, b, st)) - 1) * st + 1)
        dt = "S1" if self._kind == "S1" else self._kind
        data = np.ascontiguousarray(value, dtype=np.dtype(dt).newbyteorder("="))
        w.write(self.name, data.tobytes(), sel)
        self._shape = self.shape

    def _encode(self, value):
        value = np.ma.asarray(value) if np.ma.isMaskedArray(value) else np.asarray(value)
        if self._kind == "S1":
            return value
        if self._scale and ("scale_factor" in self._attrs or "add_offset" in self._attrs):
            scale = self._attrs.get("scale_factor", 1.0)
            offset = self._attrs.get("add_offset", 0.0)
            value = (value - offset) / scale
            if np.dtype(self._kind).kind in "iu":
                value = np.ma.round(value) if np.ma.isMaskedArray(value) else np.round(value)
        if np.ma.isMaskedArray(value):
            fill = self._attrs.get("_FillValue", self._attrs.get("missing_value", _DEFAULT_FILL.get(self._kind)))
            value = value.filled(np.atleast_1d(fill)[0])
        return value

    def chunking(self):
        return self._ds._chunks.get(self.name, "contiguous")

    def __repr__(self):
        dims = ", ".join(self.dimensions)
        return f"<nc4rs.Variable {self._kind} {self.name}({dims}), shape = {self.shape}>"


class Dataset:
    """A NetCDF file: mode "r" to read, "w" to write (written when closed)."""

    def __init__(self, filename, mode="r", clobber=True, format="NETCDF4", **kwargs):
        self.filepath_ = str(filename)
        self._reader = None
        self._writer = None
        self._chunks = {}
        self.dimensions = {}
        self.variables = {}
        self._attrs = {}
        if mode == "r":
            self._reader = Reader(self.filepath_)
            self.data_model = self._reader.format()
            for name, size, unlimited in self._reader.dimensions():
                self.dimensions[name] = Dimension(name, size, unlimited)
            for name, dims, shape, dtype, attrs in self._reader.variables():
                attrs = {a: _attr_in(k, v) for a, k, v in attrs}
                self.variables[name] = Variable(self, name, dims, shape, dtype, attrs)
            for a, k, v in self._reader.global_attributes():
                self._attrs[a] = _attr_in(k, v)
            self._measure_unlimited()
        elif mode in ("w", "x"):
            if mode == "x" or not clobber:
                import os

                if os.path.exists(self.filepath_):
                    raise FileExistsError(self.filepath_)
            self.data_model = format
            self._writer = Writer(self.filepath_, format)
        else:
            raise ValueError(f"mode {mode!r} is not supported (use 'r' or 'w')")

    def _measure_unlimited(self):
        # netcdf-rust gives 0 for the length of an unlimited dimension in NetCDF-4.
        # A read that runs past the end, 0 wide on the other axes, returns the
        # real length without reading any values.
        unlimited = {n for n, d in self.dimensions.items() if d.isunlimited()}
        for var in self.variables.values():
            if var._kind == "str" or not unlimited & set(var.dimensions):
                continue
            sel = [(0, 1 << 62, 1) if d in unlimited else (0, 0, 1) for d in var.dimensions]
            _, shape = self._reader.read(var.name, sel)
            var._shape = tuple(shape[i] if d in unlimited else n
                               for i, (d, n) in enumerate(zip(var.dimensions, var._shape)))
            for i, d in enumerate(var.dimensions):
                if d in unlimited:
                    self.dimensions[d].size = max(self.dimensions[d].size, shape[i])

    def read_many(self, names=None):
        """Read whole variables in parallel: {name: array}, decoded as by var[:]."""
        if self._reader is None:
            raise OSError("this file is open for writing")
        names = [n for n in (names or self.variables) if self.variables[n]._kind != "str"]
        raws = self._reader.read_many(names)
        return {n: self.variables[n]._from_raw(raw, shape) for n, (raw, shape) in zip(names, raws)}

    def _need_writer(self):
        if self._writer is None:
            raise OSError("this file is open for reading")
        return self._writer

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def close(self):
        if self._writer is not None:
            self._writer.close()
        self._reader = None

    def __getitem__(self, name):
        return self.variables[name]

    def createDimension(self, name, size=None):
        self._need_writer().add_dimension(name, None if size is None else int(size))
        dim = Dimension(name, 0 if size is None else int(size), size is None)
        self.dimensions[name] = dim
        return dim

    def createVariable(self, varname, datatype, dimensions=(), compression=None, zlib=False,
                       complevel=4, shuffle=True, chunksizes=None, contiguous=False,
                       fill_value=None, **kwargs):
        w = self._need_writer()
        if isinstance(dimensions, str):
            dimensions = (dimensions,)
        if datatype is str:
            kind = "str"
        elif np.dtype(datatype) == np.dtype("S1"):
            kind = "S1"
        else:
            kind = _KINDS[np.dtype(datatype).newbyteorder("=")]
        if compression not in (None, "zlib"):
            raise ValueError(f"compression {compression!r} is not supported (only zlib)")
        deflate = int(complevel) if (zlib or compression == "zlib") else None
        if chunksizes is not None:
            chunksizes = [int(c) for c in chunksizes]
            self._chunks[varname] = chunksizes
        w.add_variable(varname, kind, list(dimensions), deflate, bool(shuffle and deflate is not None), chunksizes)
        var = Variable(self, varname, dimensions, [len(self.dimensions[d]) for d in dimensions], kind, {})
        if fill_value is not None and fill_value is not False and kind not in ("str", "S1"):
            w.set_fill_value(varname, np.array(fill_value, dtype=kind).tobytes())
            var._attrs["_FillValue"] = np.array(fill_value, dtype=kind)[()]
        self.variables[varname] = var
        return var

    # Global attributes
    def ncattrs(self):
        return list(self._attrs)

    def getncattr(self, name):
        return self._attrs[name]

    def setncattr(self, name, value):
        kind, out = _attr_out(value)
        self._need_writer().add_attribute(None, name, kind, out)
        self._attrs[name] = value

    def __getattr__(self, name):
        if name.startswith("_"):
            raise AttributeError(name)
        try:
            return self._attrs[name]
        except KeyError:
            raise AttributeError(name) from None

    def __setattr__(self, name, value):
        if name.startswith("_") or name in ("dimensions", "variables", "filepath_", "data_model"):
            object.__setattr__(self, name, value)
        else:
            self.setncattr(name, value)

    def filepath(self):
        return self.filepath_

    def __repr__(self):
        return f"<nc4rs.Dataset {self.filepath_!r}: {len(self.dimensions)} dims, {len(self.variables)} vars>"


def to_netcdf(ds, path, **kwargs):
    """Write an xarray Dataset with nc4rs (see nc4rs.xarray_backend.to_netcdf)."""
    from nc4rs.xarray_backend import to_netcdf as write

    return write(ds, path, **kwargs)
