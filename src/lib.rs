use pyo3::prelude::*;

pub mod deck;
pub mod mana;
pub mod sim;
pub mod stats;

use crate::sim::run;
use crate::stats::Stats;
use crate::deck::DeckFile;

#[pyfunction]
fn run_sim(deck_path: &str, sims: usize, turns: usize) -> PyResult<Stats> {
    let f = std::fs::File::open(deck_path)
        .map_err(|e| pyo3::exceptions::PyIOError::new_err(e.to_string()))?;
    let deck: DeckFile =
        serde_json::from_reader(f).map_err(|e| pyo3::exceptions::PyValueError::new_err(e.to_string()))?;

    let stats = run(&deck, sims, turns);

    Ok(stats)
}

#[pymodule]
fn mana_sim(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(run_sim, m)?)?;
    Ok(())
}
