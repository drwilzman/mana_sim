# Mana Simulator for MTG Commander

A **Monte Carlo mana simulator** for Magic: The Gathering **Commander (EDH)** decks.  
Analyze **mana screw**, **mana flood**, curve reliability, and **optimize land counts and color ratios** using a Python → Rust simulation pipeline.

---

## What This Tool Does

- Converts human-readable decklists into structured JSON
- Runs high-volume Monte Carlo simulations in Rust
- Evaluates mana stability across multiple turns
- Optimizes **land counts and color distributions**
- Supports mono-color and multi-color commanders
- Produces plots and ranked land configurations

Designed for **real Commander decks**, not goldfish math.

---

## Core Features

### Mana Simulation
- Simulates thousands of games per configuration
- Tracks per-turn probabilities of:
  - **OK** (playable mana)
  - **Mana screw**
  - **Mana flood**
- Accounts for:
  - Colored vs generic costs
  - Ramp sources
  - Commander color identity
  - Singleton rules

### Land Optimization (`--test-lands`)
- Automatically generates land variants
- Adjusts:
  - Total land count
  - Color ratios (W/U/B/R/G)
- Enforces **exactly 99 cards excluding commander**
- Ranks configurations by mana performance
- Works for:
  - Mono-color decks
  - Multi-color commanders

### Optional Swap Testing (`--test-swaps`)
- Tests MAYBE cards against main-deck cards
- Scores replacements by mana performance impact

### Visualization
- Turn-by-turn plots:
  - OK / Screw / Flood
  - Cumulative OK probability
- Output saved automatically to `output/`

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

