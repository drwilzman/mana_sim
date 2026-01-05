use pyo3::prelude::*;
use serde::Serialize;

#[pyclass]
#[derive(Clone, Serialize)]
pub struct TurnSnapshot {
    #[pyo3(get)]
    pub turn: usize,
    #[pyo3(get)]
    pub hand: Vec<String>,
    #[pyo3(get)]
    pub battlefield: Vec<String>,
    #[pyo3(get)]
    pub played_cards: Vec<String>,
    #[pyo3(get)]
    pub mana_available: u32,
    #[pyo3(get)]
    pub mana_spent: u32,
    #[pyo3(get)]
    pub cards_cast: usize,
    #[pyo3(get)]
    pub status: String,
}

#[pyclass]
#[derive(Clone, Serialize)]
pub struct GameTrace {
    #[pyo3(get)]
    pub final_status: String,
    #[pyo3(get)]
    pub turns: Vec<TurnSnapshot>,
}

#[pyclass]
#[derive(Serialize)]
pub struct Stats {
    #[pyo3(get)]
    pub screw: Vec<f64>,
    #[pyo3(get)]
    pub flood: Vec<f64>,
    #[pyo3(get)]
    pub ok: Vec<f64>,
    
    #[pyo3(get)]
    pub avg_mana_spent: Vec<f64>,
    #[pyo3(get)]
    pub avg_mana_available: Vec<f64>,
    #[pyo3(get)]
    pub avg_cards_cast: Vec<f64>,
    #[pyo3(get)]
    pub avg_hand_size: Vec<f64>,
    
    #[pyo3(get)]
    pub example_traces: Vec<GameTrace>,
}

impl Stats {
    pub fn new(n: usize) -> Self {
        Self {
            screw: vec![0.0; n],
            flood: vec![0.0; n],
            ok: vec![0.0; n],
            avg_mana_spent: vec![0.0; n],
            avg_mana_available: vec![0.0; n],
            avg_cards_cast: vec![0.0; n],
            avg_hand_size: vec![0.0; n],
            example_traces: Vec::new(),
        }
    }
}
