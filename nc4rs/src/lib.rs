// SPDX-License-Identifier: MIT
//! The small layer between Python and netcdf-rust. Python (nc4rs/__init__.py)
//! keeps the netCDF4-like API; this module only reads and writes raw values.
//!
//! Values cross as bytes in the machine's byte order with a numpy dtype string
//! ("i2", "f4", ...), and slices as (start, stop, step) per dimension.

use std::collections::HashMap;
use std::fs::File;
use std::io::BufWriter;

use netcdf_core::{NcAttrValue, NcSliceInfo, NcSliceInfoElem, NcType};
use netcdf_reader::NcFile;
use netcdf_writer::{DimensionId, NcFileBuilder, NcWriteFormat, NcWriteOptions, VariableId};
use pyo3::exceptions::{PyIOError, PyKeyError, PyValueError};
use pyo3::prelude::*;
use pyo3::types::PyBytes;
use rayon::prelude::*;

fn io_err(e: impl std::fmt::Display) -> PyErr {
    PyIOError::new_err(e.to_string())
}

fn dtype_of(t: &NcType) -> &'static str {
    match t {
        NcType::Byte => "i1",
        NcType::UByte => "u1",
        NcType::Short => "i2",
        NcType::UShort => "u2",
        NcType::Int => "i4",
        NcType::UInt => "u4",
        NcType::Int64 => "i8",
        NcType::UInt64 => "u8",
        NcType::Float => "f4",
        NcType::Double => "f8",
        NcType::Char => "S1",
        NcType::String => "str",
        _ => "other",
    }
}

fn type_of(dtype: &str) -> PyResult<NcType> {
    Ok(match dtype {
        "i1" => NcType::Byte,
        "u1" => NcType::UByte,
        "i2" => NcType::Short,
        "u2" => NcType::UShort,
        "i4" => NcType::Int,
        "u4" => NcType::UInt,
        "i8" => NcType::Int64,
        "u8" => NcType::UInt64,
        "f4" => NcType::Float,
        "f8" => NcType::Double,
        "S1" => NcType::Char,
        "str" => NcType::String,
        _ => return Err(PyValueError::new_err(format!("unsupported dtype {dtype}"))),
    })
}

/// (dtype, value): the value is a str for text, else a list of numbers
fn attr_to_py(py: Python<'_>, v: &NcAttrValue) -> PyResult<(String, Py<PyAny>)> {
    let (kind, obj) = match v {
        NcAttrValue::Chars(s) => ("str", s.into_pyobject(py)?.into_any()),
        NcAttrValue::Strings(s) => ("strs", s.into_pyobject(py)?.into_any()),
        NcAttrValue::Bytes(x) => ("i1", x.into_pyobject(py)?.into_any()),
        NcAttrValue::UBytes(x) => ("u1", x.as_slice().into_pyobject(py)?.into_any()),
        NcAttrValue::Shorts(x) => ("i2", x.into_pyobject(py)?.into_any()),
        NcAttrValue::UShorts(x) => ("u2", x.into_pyobject(py)?.into_any()),
        NcAttrValue::Ints(x) => ("i4", x.into_pyobject(py)?.into_any()),
        NcAttrValue::UInts(x) => ("u4", x.into_pyobject(py)?.into_any()),
        NcAttrValue::Int64s(x) => ("i8", x.into_pyobject(py)?.into_any()),
        NcAttrValue::UInt64s(x) => ("u8", x.into_pyobject(py)?.into_any()),
        NcAttrValue::Floats(x) => ("f4", x.into_pyobject(py)?.into_any()),
        NcAttrValue::Doubles(x) => ("f8", x.into_pyobject(py)?.into_any()),
    };
    Ok((kind.to_string(), obj.unbind()))
}

fn attr_from_py(kind: &str, value: &Bound<'_, PyAny>) -> PyResult<NcAttrValue> {
    Ok(match kind {
        "str" => NcAttrValue::Chars(value.extract()?),
        "strs" => NcAttrValue::Strings(value.extract()?),
        "i1" => NcAttrValue::Bytes(value.extract()?),
        "u1" => NcAttrValue::UBytes(value.extract()?),
        "i2" => NcAttrValue::Shorts(value.extract()?),
        "u2" => NcAttrValue::UShorts(value.extract()?),
        "i4" => NcAttrValue::Ints(value.extract()?),
        "u4" => NcAttrValue::UInts(value.extract()?),
        "i8" => NcAttrValue::Int64s(value.extract()?),
        "u8" => NcAttrValue::UInt64s(value.extract()?),
        "f4" => NcAttrValue::Floats(value.extract()?),
        "f8" => NcAttrValue::Doubles(value.extract()?),
        _ => return Err(PyValueError::new_err(format!("unsupported attribute type {kind}"))),
    })
}

fn selection(sel: &[(u64, u64, u64)]) -> NcSliceInfo {
    NcSliceInfo {
        selections: sel
            .iter()
            .map(|&(start, end, step)| NcSliceInfoElem::Slice { start, end, step })
            .collect(),
    }
}

/// Plain values that cross as bytes in the machine's byte order
trait Plain: Copy {
    const SIZE: usize;
    fn get(b: &[u8]) -> Self;
}

macro_rules! plain {
    ($($t:ty),*) => {$(
        impl Plain for $t {
            const SIZE: usize = std::mem::size_of::<$t>();
            fn get(b: &[u8]) -> Self { <$t>::from_ne_bytes(b.try_into().unwrap()) }
        }
    )*};
}
plain!(i8, u8, i16, u16, i32, u32, i64, u64, f32, f64);

fn to_bytes<T: Plain>(a: ndarray::ArrayD<T>) -> (Vec<u8>, Vec<usize>) {
    let shape = a.shape().to_vec();
    let a = a.as_standard_layout();
    let s = a.as_slice().expect("standard layout");
    // SAFETY: T is a plain number type, so its values are plain bytes
    let bytes = unsafe { std::slice::from_raw_parts(s.as_ptr() as *const u8, std::mem::size_of_val(s)) };
    (bytes.to_vec(), shape)
}

fn read_raw(f: &NcFile, name: &str, sel: Option<&NcSliceInfo>) -> Result<(Vec<u8>, Vec<usize>), String> {
    let var = f.variable(name).map_err(|e| e.to_string())?;
    let all = NcSliceInfo::all(var.ndim());
    let s = sel.unwrap_or(&all);
    macro_rules! get {
        ($ty:ty) => {
            f.read_variable_slice_parallel::<$ty>(name, s).map(to_bytes).map_err(|e| e.to_string())
        };
    }
    match var.dtype() {
        NcType::Byte => get!(i8),
        NcType::UByte | NcType::Char => get!(u8),
        NcType::Short => get!(i16),
        NcType::UShort => get!(u16),
        NcType::Int => get!(i32),
        NcType::UInt => get!(u32),
        NcType::Int64 => get!(i64),
        NcType::UInt64 => get!(u64),
        NcType::Float => get!(f32),
        NcType::Double => get!(f64),
        t => Err(format!("reading {t:?} is not supported")),
    }
}

fn from_bytes<T: Plain>(b: &[u8]) -> PyResult<Vec<T>> {
    if b.len() % T::SIZE != 0 {
        return Err(PyValueError::new_err("data length does not match the dtype"));
    }
    Ok(b.chunks_exact(T::SIZE).map(T::get).collect())
}

#[pyclass(module = "nc4rs._nc4rs")]
struct Reader {
    f: NcFile,
}

#[pymethods]
impl Reader {
    #[new]
    fn new(path: &str) -> PyResult<Self> {
        Ok(Reader { f: NcFile::open(path).map_err(io_err)? })
    }

    fn format(&self) -> String {
        format!("{:?}", self.f.format())
    }

    /// [(name, size, unlimited)]
    fn dimensions(&self) -> PyResult<Vec<(String, u64, bool)>> {
        Ok(self
            .f
            .dimensions()
            .map_err(io_err)?
            .iter()
            .map(|d| (d.name.clone(), d.size, d.is_unlimited))
            .collect())
    }

    /// [(name, dimension names, shape, dtype, [(attribute, type, value)])]
    #[allow(clippy::type_complexity)]
    fn variables(
        &self,
        py: Python<'_>,
    ) -> PyResult<Vec<(String, Vec<String>, Vec<u64>, String, Vec<(String, String, Py<PyAny>)>)>> {
        let mut out = Vec::new();
        for v in self.f.variables().map_err(io_err)? {
            let mut attrs = Vec::new();
            for a in v.attributes() {
                let (kind, value) = attr_to_py(py, &a.value)?;
                attrs.push((a.name.clone(), kind, value));
            }
            out.push((
                v.name().to_string(),
                v.dimensions().iter().map(|d| d.name.clone()).collect(),
                v.shape(),
                dtype_of(v.dtype()).to_string(),
                attrs,
            ));
        }
        Ok(out)
    }

    fn global_attributes(&self, py: Python<'_>) -> PyResult<Vec<(String, String, Py<PyAny>)>> {
        let mut out = Vec::new();
        for a in self.f.global_attributes().map_err(io_err)? {
            let (kind, value) = attr_to_py(py, &a.value)?;
            out.push((a.name.clone(), kind, value));
        }
        Ok(out)
    }

    /// Raw values of a slice: (bytes, shape). The chunks are read in parallel.
    fn read<'py>(
        &self,
        py: Python<'py>,
        name: &str,
        sel: Vec<(u64, u64, u64)>,
    ) -> PyResult<(Bound<'py, PyBytes>, Vec<usize>)> {
        self.f.variable(name).map_err(|e| PyKeyError::new_err(e.to_string()))?;
        let s = selection(&sel);
        let f = &self.f;
        let (bytes, shape) = py.detach(|| read_raw(f, name, Some(&s))).map_err(io_err)?;
        Ok((PyBytes::new(py, &bytes), shape))
    }

    /// Raw values of whole variables, read in parallel: [(bytes, shape)]
    fn read_many<'py>(
        &self,
        py: Python<'py>,
        names: Vec<String>,
    ) -> PyResult<Vec<(Bound<'py, PyBytes>, Vec<usize>)>> {
        let f = &self.f;
        let out: Vec<Result<(Vec<u8>, Vec<usize>), String>> =
            py.detach(|| names.par_iter().map(|n| read_raw(f, n, None)).collect());
        out.into_iter()
            .map(|r| r.map(|(b, shape)| (PyBytes::new(py, &b), shape)).map_err(io_err))
            .collect()
    }

    /// Whole string variable as a flat list
    fn read_strings(&self, name: &str) -> PyResult<Vec<String>> {
        self.f.read_variable_as_strings(name).map_err(io_err)
    }
}

#[pyclass(module = "nc4rs._nc4rs")]
struct Writer {
    b: Option<NcFileBuilder>,
    path: String,
    format: NcWriteFormat,
    dims: HashMap<String, DimensionId>,
    vars: HashMap<String, (VariableId, NcType)>,
}

impl Writer {
    fn builder(&mut self) -> PyResult<&mut NcFileBuilder> {
        self.b.as_mut().ok_or_else(|| PyIOError::new_err("the file is closed"))
    }

    fn var(&self, name: &str) -> PyResult<(VariableId, NcType)> {
        self.vars
            .get(name)
            .cloned()
            .ok_or_else(|| PyKeyError::new_err(format!("no variable {name}")))
    }
}

#[pymethods]
impl Writer {
    #[new]
    fn new(path: &str, format: &str) -> PyResult<Self> {
        let format = match format {
            "NETCDF4" => NcWriteFormat::Nc4,
            "NETCDF4_CLASSIC" => NcWriteFormat::Nc4Classic,
            "NETCDF3_CLASSIC" => NcWriteFormat::Classic,
            "NETCDF3_64BIT_OFFSET" => NcWriteFormat::Offset64,
            "NETCDF3_64BIT_DATA" => NcWriteFormat::Cdf5,
            _ => return Err(PyValueError::new_err(format!("unsupported format {format}"))),
        };
        // Fail now, not at close, if the file cannot be made
        File::create(path).map_err(io_err)?;
        Ok(Writer {
            b: Some(NcFileBuilder::new()),
            path: path.to_string(),
            format,
            dims: HashMap::new(),
            vars: HashMap::new(),
        })
    }

    #[pyo3(signature = (name, size=None))]
    fn add_dimension(&mut self, name: &str, size: Option<u64>) -> PyResult<()> {
        let b = self.builder()?;
        let id = match size {
            Some(n) => b.add_dimension(name, n),
            None => b.add_unlimited_dimension(name),
        }
        .map_err(io_err)?;
        self.dims.insert(name.to_string(), id);
        Ok(())
    }

    #[pyo3(signature = (name, dtype, dims, deflate=None, shuffle=false, chunks=None))]
    fn add_variable(
        &mut self,
        name: &str,
        dtype: &str,
        dims: Vec<String>,
        deflate: Option<u8>,
        shuffle: bool,
        chunks: Option<Vec<u64>>,
    ) -> PyResult<()> {
        let t = type_of(dtype)?;
        let ids = dims
            .iter()
            .map(|d| {
                self.dims
                    .get(d)
                    .copied()
                    .ok_or_else(|| PyKeyError::new_err(format!("no dimension {d}")))
            })
            .collect::<PyResult<Vec<_>>>()?;
        let b = self.builder()?;
        let id = match t {
            NcType::Byte => b.add_variable::<i8>(name, &ids),
            NcType::UByte => b.add_variable::<u8>(name, &ids),
            NcType::Short => b.add_variable::<i16>(name, &ids),
            NcType::UShort => b.add_variable::<u16>(name, &ids),
            NcType::Int => b.add_variable::<i32>(name, &ids),
            NcType::UInt => b.add_variable::<u32>(name, &ids),
            NcType::Int64 => b.add_variable::<i64>(name, &ids),
            NcType::UInt64 => b.add_variable::<u64>(name, &ids),
            NcType::Float => b.add_variable::<f32>(name, &ids),
            NcType::Double => b.add_variable::<f64>(name, &ids),
            NcType::Char => b.add_char_variable(name, &ids),
            NcType::String => b.add_string_variable(name, &ids),
            _ => unreachable!(),
        }
        .map_err(io_err)?;
        if let Some(c) = chunks {
            b.set_variable_chunking(id, c).map_err(io_err)?;
        }
        if deflate.is_some() {
            b.set_variable_deflate(id, deflate, shuffle).map_err(io_err)?;
        } else if shuffle {
            b.set_variable_shuffle(id, true).map_err(io_err)?;
        }
        self.vars.insert(name.to_string(), (id, t));
        Ok(())
    }

    /// The fill value, given as bytes of one value in the machine's byte order
    fn set_fill_value(&mut self, name: &str, value: &[u8]) -> PyResult<()> {
        let (id, t) = self.var(name)?;
        let b = self.builder()?;
        match t {
            NcType::Byte => b.set_variable_fill_value(id, i8::get(value)),
            NcType::UByte => b.set_variable_fill_value(id, u8::get(value)),
            NcType::Short => b.set_variable_fill_value(id, i16::get(value)),
            NcType::UShort => b.set_variable_fill_value(id, u16::get(value)),
            NcType::Int => b.set_variable_fill_value(id, i32::get(value)),
            NcType::UInt => b.set_variable_fill_value(id, u32::get(value)),
            NcType::Int64 => b.set_variable_fill_value(id, i64::get(value)),
            NcType::UInt64 => b.set_variable_fill_value(id, u64::get(value)),
            NcType::Float => b.set_variable_fill_value(id, f32::get(value)),
            NcType::Double => b.set_variable_fill_value(id, f64::get(value)),
            _ => return Err(PyValueError::new_err("no fill value for this type")),
        }
        .map_err(io_err)
    }

    /// An attribute of a variable, or of the file when var is None
    #[pyo3(signature = (var, name, kind, value))]
    fn add_attribute(
        &mut self,
        var: Option<&str>,
        name: &str,
        kind: &str,
        value: &Bound<'_, PyAny>,
    ) -> PyResult<()> {
        let v = attr_from_py(kind, value)?;
        let id = var.map(|n| self.var(n)).transpose()?;
        let b = self.builder()?;
        match id {
            Some((id, _)) => b.add_variable_attribute(id, name, v),
            None => b.add_attribute(name, v),
        }
        .map_err(io_err)
    }

    /// Values of a slice (or the whole variable when sel is None) as bytes
    #[pyo3(signature = (name, data, sel=None))]
    fn write(&mut self, name: &str, data: &[u8], sel: Option<Vec<(u64, u64, u64)>>) -> PyResult<()> {
        let (id, t) = self.var(name)?;
        let s = sel.map(|s| selection(&s));
        let b = self.builder()?;
        macro_rules! put {
            ($ty:ty) => {{
                let v = from_bytes::<$ty>(data)?;
                match &s {
                    Some(s) => b.write_variable_slice(id, s, &v),
                    None => b.write_variable(id, &v),
                }
            }};
        }
        match t {
            NcType::Byte => put!(i8),
            NcType::UByte => put!(u8),
            NcType::Short => put!(i16),
            NcType::UShort => put!(u16),
            NcType::Int => put!(i32),
            NcType::UInt => put!(u32),
            NcType::Int64 => put!(i64),
            NcType::UInt64 => put!(u64),
            NcType::Float => put!(f32),
            NcType::Double => put!(f64),
            NcType::Char => match &s {
                Some(s) => b.write_char_variable_slice(id, s, data),
                None => b.write_char_variable(id, data),
            },
            _ => return Err(PyValueError::new_err("use write_strings for strings")),
        }
        .map_err(io_err)
    }

    fn write_strings(&mut self, name: &str, values: Vec<String>) -> PyResult<()> {
        let (id, _) = self.var(name)?;
        self.builder()?.write_string_variable(id, &values).map_err(io_err)
    }

    /// Write the file. The values are compressed in parallel.
    fn close(&mut self, py: Python<'_>) -> PyResult<()> {
        let Some(b) = self.b.take() else { return Ok(()) };
        let path = self.path.clone();
        let format = self.format;
        py.detach(move || -> PyResult<()> {
            let file = BufWriter::new(File::create(&path).map_err(io_err)?);
            b.write(file, NcWriteOptions { format }).map_err(io_err)?;
            Ok(())
        })
    }
}

#[pymodule]
fn _nc4rs(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_class::<Reader>()?;
    m.add_class::<Writer>()?;
    m.add("__version__", env!("CARGO_PKG_VERSION"))?;
    Ok(())
}
