# SPDX-License-Identifier: MIT
"""python -m unittest discover tests   (needs numpy, netCDF4 and xarray)

Each test writes with one library and reads with the other, and checks that the
values, attributes and masks are the same. netCDF4 (libnetcdf) is the reference.
"""
import os
import tempfile
import unittest

import netCDF4
import numpy as np
import xarray as xr

import nc4rs

RNG = np.random.default_rng(7)


class Nc4rs(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.dir.cleanup()

    def path(self, name):
        return os.path.join(self.dir.name, name)

    def test_written_by_nc4rs_is_read_by_netcdf4(self):
        p = self.path("a.nc")
        t = RNG.normal(15, 10, (4, 5, 6)).astype("f4")
        with nc4rs.Dataset(p, "w") as ds:
            ds.title = "test"
            ds.createDimension("time", None)
            ds.createDimension("lat", 5)
            ds.createDimension("lon", 6)
            lat = ds.createVariable("lat", "f8", ("lat",))
            lat.units = "degrees_north"
            lat[:] = np.linspace(30, 40, 5)
            v = ds.createVariable("t2m", "i2", ("time", "lat", "lon"), zlib=True, complevel=4,
                                  chunksizes=(1, 5, 6), fill_value=-32767)
            v.scale_factor = 0.01
            v.add_offset = 10.0
            v.units = "degC"
            data = np.ma.masked_array(t, mask=t > 30)
            v[:] = data
        with netCDF4.Dataset(p) as ds:
            self.assertEqual(ds.title, "test")
            self.assertTrue(ds.dimensions["time"].isunlimited())
            self.assertEqual(len(ds.dimensions["time"]), 4)
            np.testing.assert_allclose(ds["lat"][:], np.linspace(30, 40, 5))
            got = ds["t2m"][:]
            self.assertEqual(ds["t2m"].filters()["zlib"], True)
            self.assertEqual(ds["t2m"].chunking(), [1, 5, 6])
            np.testing.assert_array_equal(got.mask, data.mask)
            np.testing.assert_allclose(got.compressed(), np.round((data.compressed() - 10) / 0.01) * 0.01 + 10,
                                       atol=1e-6)

    def test_written_by_netcdf4_is_read_by_nc4rs(self):
        p = self.path("b.nc")
        raw = RNG.integers(-2000, 2000, (3, 7, 9)).astype("i2")
        raw[0, 0, :3] = -32767
        with netCDF4.Dataset(p, "w") as ds:
            ds.createDimension("time", None)
            ds.createDimension("y", 7)
            ds.createDimension("x", 9)
            v = ds.createVariable("q", "i2", ("time", "y", "x"), zlib=True, shuffle=True,
                                  chunksizes=(1, 4, 5), fill_value=-32767)
            v.scale_factor = np.float32(0.5)
            v.add_offset = np.float32(10.0)
            v.set_auto_maskandscale(False)
            v[:] = raw
            ds.createVariable("name", str, ())  # a scalar string
            ds["name"][...] = "abc"
        with netCDF4.Dataset(p) as ref, nc4rs.Dataset(p) as ds:
            self.assertEqual(set(ds.variables), set(ref.variables))
            for key in (slice(None), (1, slice(2, 6), slice(None, None, 2)), (Ellipsis, 3),
                        (slice(None), [0, 3, 6], 4), (-1, slice(None, None, -1))):
                a, b = ref["q"][key], ds["q"][key]
                np.testing.assert_array_equal(np.ma.getmaskarray(a), np.ma.getmaskarray(b))
                np.testing.assert_allclose(a.filled(0), b.filled(0))
            ds["q"].set_auto_maskandscale(False)
            np.testing.assert_array_equal(ds["q"][:], raw)

    def test_xarray_reads_the_same(self):
        p = self.path("c.nc")
        ds0 = xr.Dataset(
            {"tp": (("time", "lat"), RNG.random((5, 4)).astype("f4"))},
            coords={"time": np.arange("2026-10-01", "2026-10-06", dtype="datetime64[D]"),
                    "lat": [30.0, 31.0, 32.0, 33.0]},
            attrs={"source": "test"},
        )
        ds0["tp"].attrs["units"] = "m"
        enc = {"tp": {"dtype": "i2", "scale_factor": 1e-4, "_FillValue": -32767, "zlib": True}}
        ds0.to_netcdf(p, encoding=enc, engine="netcdf4")
        a = xr.open_dataset(p, engine="netcdf4").load()
        b = xr.open_dataset(p, engine="nc4rs").load()
        xr.testing.assert_identical(a, b)

    def test_xarray_writes_with_nc4rs(self):
        p = self.path("d.nc")
        ds0 = xr.Dataset({"u": (("y", "x"), RNG.normal(0, 5, (6, 8)))},
                         coords={"y": np.arange(6.0), "x": np.arange(8.0)})
        nc4rs.to_netcdf(ds0, p, encoding={"u": {"dtype": "i2", "scale_factor": 0.01, "zlib": True,
                                                "_FillValue": -32767}})
        back = xr.open_dataset(p, engine="netcdf4").load()
        np.testing.assert_allclose(back["u"].values, ds0["u"].values, atol=0.005)
        np.testing.assert_array_equal(back["x"].values, ds0["x"].values)

    def test_random_variables_both_ways(self):
        """Random shapes, types, chunks, compression and missing values, both directions."""
        rng = np.random.default_rng(2026)
        for case in range(60):
            dtype = rng.choice(["i1", "u1", "i2", "u2", "i4", "u4", "i8", "f4", "f8"])
            ndim = int(rng.integers(1, 4))
            shape = tuple(int(n) for n in rng.integers(1, 9, ndim))
            if np.dtype(dtype).kind == "f":
                raw = rng.normal(0, 100, shape).astype(dtype)
            else:
                info = np.iinfo(dtype)
                raw = rng.integers(max(info.min, -1000) + 2, min(info.max, 1000) - 2, shape).astype(dtype)
            fill = np.array(np.iinfo(dtype).max if np.dtype(dtype).kind == "u" else -99, dtype=dtype)[()]
            raw.flat[int(rng.integers(0, raw.size))] = fill
            zlib = bool(rng.integers(0, 2))
            chunks = tuple(int(rng.integers(1, n + 1)) for n in shape) if zlib or rng.integers(0, 2) else None
            dims = [f"d{i}" for i in range(ndim)]
            for writer, reader in ((nc4rs, netCDF4), (netCDF4, nc4rs)):
                p = self.path(f"r{case}-{writer.__name__}.nc")
                with writer.Dataset(p, "w") as ds:
                    for d, n in zip(dims, shape):
                        ds.createDimension(d, n)
                    v = ds.createVariable("v", dtype, dims, zlib=zlib, chunksizes=chunks, fill_value=fill)
                    v.set_auto_maskandscale(False)
                    v[:] = raw
                with reader.Dataset(p) as ds:
                    got = ds["v"][:]
                    msg = f"case {case} {writer.__name__}->{reader.__name__} {dtype} {shape} {chunks} {zlib}"
                    np.testing.assert_array_equal(np.ma.getmaskarray(got), raw == fill, err_msg=msg)
                    np.testing.assert_array_equal(np.ma.getdata(got), raw, err_msg=msg)

    def test_xarray_scalar_coordinates_stay_coordinates(self):
        """Written by nc4rs.to_netcdf, the file reads back as the same as one by netCDF4."""
        ds0 = xr.Dataset(
            {"t2m": (("lat", "lon"), RNG.normal(280, 10, (3, 4)))},
            coords={"lat": [30.0, 31.0, 32.0], "lon": [130.0, 131.0, 132.0, 133.0],
                    "time": np.datetime64("2026-10-13T00:00"), "step": np.timedelta64(72, "h"),
                    "heightAboveGround": 2.0},
        )
        enc = {"t2m": {"dtype": "i2", "scale_factor": 0.01, "add_offset": 280.0,
                       "_FillValue": -32767, "zlib": True}}
        ds0.to_netcdf(self.path("ref.nc"), engine="netcdf4", encoding=enc)
        nc4rs.to_netcdf(ds0, self.path("ours.nc"), encoding=enc)
        for mask_and_scale in (False, True):
            a = xr.open_dataset(self.path("ref.nc"), engine="netcdf4", mask_and_scale=mask_and_scale).load()
            b = xr.open_dataset(self.path("ours.nc"), engine="netcdf4", mask_and_scale=mask_and_scale).load()
            self.assertEqual(list(b.data_vars), ["t2m"])
            xr.testing.assert_identical(a, b)

    def test_classic_format(self):
        p = self.path("e.nc")
        with nc4rs.Dataset(p, "w", format="NETCDF3_CLASSIC") as ds:
            ds.createDimension("x", 4)
            v = ds.createVariable("v", "f4", ("x",))
            v[:] = [1, 2, 3, 4]
        with netCDF4.Dataset(p) as ds:
            self.assertEqual(ds.data_model, "NETCDF3_CLASSIC")
            np.testing.assert_array_equal(ds["v"][:], [1, 2, 3, 4])


if __name__ == "__main__":
    unittest.main()
