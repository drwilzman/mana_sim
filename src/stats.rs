use pyo3::prelude::*;
use serde::Serialize;

#[derive(Clone, Serialize)]
pub struct TurnSnapshot {
    pub turn: usize,
    pub hand: Vec<String>,
    pub battlefield: Vec<String>,
    pub mana_available: u32,
    pub mana_spent: u32,
    pub cards_cast: usize,
    pub status: String, // "screw", "flood", "ok"
}

#[derive(Clone, Serialize)]
pub struct GameTrace {
    pub final_status: String, // Dominant status across game
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
    
    #[serde(skip)]
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
