# Mana Simulator for MTG Commander

Simulate mana screw, mana flood, and playable hands for Magic: The Gathering Commander decks.  
This project lets you test your deck's mana reliability by running Monte Carlo simulations over multiple turns.

---

## Features

- Parse decklists from text files into structured JSON.
- Simulate hundreds or thousands of games to calculate **mana screw**, **mana flood**, and playable turns.
- Track colored and generic mana requirements.
- Works with singleton rules for Commander decks.
- Generate example graphs of simulation results (Python optional).

---

## Folder Structure
mana_sim/
├─ decks/ # Deck JSON files (auto-generated or custom)
├─ output/ # Example graphs & simulation outputs
├─ src/ # Rust source files
│ ├─ deck.rs
│ ├─ lib.rs
│ ├─ mana.rs
│ ├─ sim.rs
│ └─ stats.rs
├─ target/ # Rust build artifacts (auto)
├─ decklist.txt # Example decklist (text format)
├─ demo.py # Demo script to parse & run simulations
├─ parse_deck.py # Python parser: decklist -> JSON
├─ README.md # Project documentation
├─ Cargo.toml # Rust package manifest
├─ Cargo.lock
├─ pyproject.toml # Optional Python project file

---

## Getting Started

### Requirements

- Rust ≥ 1.70  
- Python 3.x (for `parse_deck.py`)  
- Python packages: `requests` (`pip install requests`)

---

### Step 1: Convert Decklist to JSON

Example text decklist `decklist.txt`:

Run parser:

```bash
python parse_deck.py \
  --input decklist.txt \
  --output decks/vampire.json \
  --commander "Queen Marchesa"
```

Converts decklist into JSON with mana costs, types, and counts.

Auto-fetches card info from Scryfall API.

Step 2: Run Mana Simulation
cargo run --release --example run_sim decks/vampire.json


Simulation outputs per turn:

Turn 1: Screw 0.12, Flood 0.03, OK 0.85
Turn 2: Screw 0.10, Flood 0.05, OK 0.85
...
Turn 10: Screw 0.02, Flood 0.15, OK 0.83


Screw: No spells playable

Flood: Too much unused mana

OK: Playable hand

Optional: Adjust Simulation Parameters


You can modify run_sim.rs to change:

*Number of simulations (sims)

*Number of turns (turns)

*Example Graphs

Python scripts can be added to generate:

*Turn-by-turn screw/flood/ok graphs

*Deck comparison charts

*Save outputs to the output/ folder.

Please keep singleton rules and Commander legality in mind when adding cards.

License:

MIT License
Feel free to use, modify, and share!

