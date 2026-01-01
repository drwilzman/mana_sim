# Mana Simulator for MTG Commander

Simulate **mana screw**, **mana flood**, and playable hands for Magic: The Gathering Commander decks. Test your deck's mana reliability by running Monte Carlo simulations over multiple turns.

---

## Features

- Parse decklists from text files into structured JSON.
- Simulate hundreds or thousands of games to calculate:
  - **Mana screw** – no spells playable
  - **Mana flood** – too much unused mana
  - **Playable hands** – playable mana on curve
- Track colored and generic mana requirements.
- Fully compatible with **Commander singleton rules**.
- Optional Python support for visualization and analysis.

---

## Folder Structure

mana_sim/
├─ decks/           # Deck JSON files (auto-generated or custom)
├─ output/          # Simulation outputs and graphs
├─ src/             # Rust source files
│  ├─ deck.rs
│  ├─ lib.rs
│  ├─ mana.rs
│  ├─ sim.rs
│  └─ stats.rs
├─ target/          # Rust build artifacts
├─ decklist.txt     # Example decklist (text format)
├─ demo.py          # Demo script to parse & run simulations
├─ parse_deck.py    # Python parser: decklist -> JSON
├─ README.md        # Project documentation
├─ Cargo.toml       # Rust package manifest
├─ Cargo.lock
└─ pyproject.toml   # Optional Python project file

---

## Getting Started

### Requirements

- Rust ≥ 1.70
- Python 3.x (for `parse_deck.py`)
- Python package: `requests` (`pip install requests`)

---

## Usage

### Convert Decklist to JSON

Given a text decklist (`decklist.txt`), run:

python parse_deck.py --input decklist.txt --output decks/vampire.json --commander "Queen Marchesa"

This converts the decklist into structured JSON with mana costs, card types, and counts. Card metadata is automatically fetched from the Scryfall API.

---

### Run Mana Simulation

cargo run --release --example run_sim decks/vampire.json

Example output:

Turn 1: Screw 0.12, Flood 0.03, OK 0.85  
Turn 2: Screw 0.10, Flood 0.05, OK 0.85  
...  
Turn 10: Screw 0.02, Flood 0.15, OK 0.83  

Definitions:
- Screw: No spells playable
- Flood: Excess unused mana
- OK: At least one reasonable play available

---

## Configuration

Simulation behavior can be adjusted in `run_sim.rs`:
- Number of simulations (`sims`)
- Number of turns (`turns`)

Optional Python scripts may be added to generate:
- Turn-by-turn screw / flood / OK plots
- Deck comparison charts

All generated artifacts can be written to the `output/` directory.

---

## Contributing

- Fork the repository
- Make your changes
- Submit a pull request

Please respect Commander legality and singleton rules when modifying deck logic.

---

## License

MIT License — free to use, modify, and share

