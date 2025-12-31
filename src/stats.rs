use pyo3::prelude::*;

/// Statistics per turn for Python
#[pyclass]
pub struct Stats {
    #[pyo3(get)]
    pub screw: Vec<f64>,
    #[pyo3(get)]
    pub flood: Vec<f64>,
    #[pyo3(get)]
    pub ok: Vec<f64>,
}

impl Stats {
    pub fn new(n: usize) -> Self {
        Self {
            screw: vec![0.0; n],
            flood: vec![0.0; n],
            ok: vec![0.0; n],
        }
    }
}

