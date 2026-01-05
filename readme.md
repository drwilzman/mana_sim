# EDH Deck Analyzer

A Python toolkit for ingesting, encoding, and simulating Magic: The Gathering EDH/Commander decks. Combines deck parsing, mechanical feature extraction, and statistical simulations to evaluate deck performance and probability outcomes.

---

## Features

### 1. Deck Encoder

- **Deck Ingestion**
  - Parses EDH decklists from plain text.
  - Stops at `maybe` sections; optional cards are not included in the main analysis.

- **Card Data**
  - Uses a local Scryfall cache (`oracle-cards.json`) for fast lookups.
  - Automatically fetches missing cards from Scryfall API.

- **Mechanical Feature Extraction**
  - Detects mana rocks, dorks, rituals, ramp, card draw, removal, token generation, life gain/loss, sacrifice/death triggers, tribal synergies, and more.
  - Tracks costs and activation timing (instant, sorcery, triggered, activated).
  - Encodes data into structured JSON for downstream analysis.

- **Deck Validation**
  - Ensures color identity legality.
  - Flags missing or illegal cards.

- **Output**
  - Encoded JSON (`output/<deck_name>_encoded.json`).
  - Optional visualization (`output/<deck_name>_encoded.png`) showing mana curve, feature distribution, and power components.

---

### 2. Deck Simulator

- **Opening Hand Analysis**
  - Computes probabilities for specific card types and mana combinations.
  - Supports hypergeometric-based calculation for starting hands.

- **Mulligan Simulation**
  - Standard and London mulligan rules.
  - Monte Carlo simulation to estimate success rates over multiple games.

- **Mana Screw / Flood Analysis**
  - Evaluates likelihood of mana issues on early turns.
  - Provides visual breakdown by turn and card type.

- **Turn-Based Simulation**
  - Optional: simulate up to `N` turns for resource development and card draw.
  - Can be extended to model combo or synergy execution probabilities.

- **Output**
  - Simulation results in JSON.
  - Graphs for hand distributions, land drops, and mulligan success rates.

---


