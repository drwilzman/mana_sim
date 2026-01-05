use crate::deck::{Card, DeckFile};
use crate::stats::{Stats, GameTrace, TurnSnapshot};
use rand::seq::SliceRandom;
use rand::thread_rng;
use rayon::prelude::*;
use std::collections::HashMap;
use std::sync::Mutex;

#[derive(Clone)]
struct ManaPool {
    generic: u32,
    colors: HashMap<String, u32>,
}

impl ManaPool {
    fn new() -> Self {
        let mut colors = HashMap::new();
        for c in &["W", "U", "B", "R", "G", "C"] {
            colors.insert(c.to_string(), 0);
        }
        ManaPool { generic: 0, colors }
    }

    fn add_color(&mut self, c: &str, n: u32) {
        *self.colors.entry(c.to_string()).or_insert(0) += n;
    }

    fn total(&self) -> u32 {
        self.generic + self.colors.values().sum::<u32>()
    }

    fn can_pay(&self, generic: u32, pips: &[String]) -> bool {
        let mut required_colors: HashMap<String, u32> = HashMap::new();
        for p in pips {
            *required_colors.entry(p.clone()).or_insert(0) += 1;
        }
        
        for (color, needed) in &required_colors {
            if self.colors.get(color).copied().unwrap_or(0) < *needed {
                return false;
            }
        }
        
        let mut remaining_mana = self.generic;
        for (color, count) in &self.colors {
            let used = required_colors.get(color).copied().unwrap_or(0);
            remaining_mana += count.saturating_sub(used);
        }
        
        remaining_mana >= generic
    }

    fn spend(&mut self, generic: u32, pips: &[String]) -> bool {
        if !self.can_pay(generic, pips) {
            return false;
        }
        
        // First, pay colored requirements
        let mut pip_counts: HashMap<String, u32> = HashMap::new();
        for p in pips {
            *pip_counts.entry(p.clone()).or_insert(0) += 1;
        }
        
        for (color, count) in pip_counts {
            *self.colors.entry(color).or_insert(0) -= count;
        }
        
        // Then pay generic costs with remaining mana
        let mut remaining = generic;
        
        // Use generic mana first
        let from_generic = remaining.min(self.generic);
        self.generic -= from_generic;
        remaining -= from_generic;
        
        // Then use any leftover colored mana for generic costs
        if remaining > 0 {
            for color_count in self.colors.values_mut() {
                if remaining == 0 { break; }
                let from_color = remaining.min(*color_count);
                *color_count -= from_color;
                remaining -= from_color;
            }
        }
        
        true
    }
}

struct GameState {
    hand: Vec<Card>,
    battlefield: Vec<Card>,
    graveyard: Vec<Card>,
    library: Vec<Card>,
    commander: Option<Card>,
    commander_casts: u32,
    lands_played: usize,
}

impl GameState {
    fn new(mut library: Vec<Card>, commander: Card) -> Self {
        library.shuffle(&mut thread_rng());
        let mut hand = Vec::new();
        for _ in 0..7 {
            if let Some(c) = library.pop() {
                hand.push(c);
            }
        }
        
        // Mulligan logic: keep if 3-5 lands
        let mut hand_size = 7;

        loop {
            hand.clear();
            library.shuffle(&mut thread_rng());

            for _ in 0..hand_size {
                if let Some(c) = library.pop() {
                    hand.push(c);
                }
            }

            let land_count = hand.iter().filter(|c| matches!(c, Card::Land { .. })).count();
            let fast_mana = hand.iter().filter(|c| {
                matches!(c, Card::Ramp { generic, .. } if *generic <= 2)
            }).count();

            let total_sources = land_count + fast_mana;

            let keep = total_sources >= 3 && land_count <= 5;

            if keep || hand_size == 4 {
                break;
            }

            // put cards back before next mull
            library.extend(hand.drain(..));
            hand_size -= 1;
        }


        GameState {
            hand,
            battlefield: Vec::new(),
            graveyard: Vec::new(),
            library,
            commander: Some(commander),
            commander_casts: 0,
            lands_played: 0,
        }
    }

    fn draw(&mut self, n: usize) {
        for _ in 0..n {
            if let Some(c) = self.library.pop() {
                self.hand.push(c);
            }
        }
    }

    fn discard_to_hand_size(&mut self, max_size: usize) {
        while self.hand.len() > max_size {
            if let Some(c) = self.hand.pop() {
                self.graveyard.push(c);
            }
        }
    }

    fn generate_mana(&self) -> ManaPool {
        let mut mana = ManaPool::new();
        for permanent in &self.battlefield {
            match permanent {
                Card::Land { produces, .. } => {
                    if produces.is_empty() {
                        continue;
                    } else if produces.len() > 1 {
                        mana.generic += 1;
                    } else {
                        let c = &produces[0];
                        if c == "C" {
                            mana.generic += 1;
                        } else {
                            mana.add_color(c, 1);
                        }
                    }
                }
                Card::Ramp { produces, .. } => {
                    if produces.is_empty() {
                        continue;
                    } else if produces.len() > 1 {
                        mana.generic += 1;
                    } else {
                        let c = &produces[0];
                        if c == "C" {
                            mana.generic += 1;
                        } else {
                            mana.add_color(c, 1);
                        }
                    }
                }
                _ => {}
            }
        }
        mana
    }
}

fn play_turn(state: &mut GameState, turn: usize) -> (u32, u32, usize, Vec<String>) {
    state.lands_played = 0;
    let mut played_cards = Vec::new();

    state.draw(1);

    // Play land
    if let Some(pos) = state.hand.iter().position(|c| matches!(c, Card::Land { .. })) {
        let land = state.hand.remove(pos);
        
        // Handle fetch lands
        if let Card::Land { is_fetch: true, fetches, name, .. } = &land {
            played_cards.push(format!("{} (fetch)", name));
            // Search library for a basic land matching fetch colors
            if let Some(basic_pos) = state.library.iter().position(|c| {
                if let Card::Land { produces, is_fetch: false, .. } = c {
                    fetches.iter().any(|f| produces.contains(f))
                } else {
                    false
                }
            }) {
                let basic = state.library.remove(basic_pos);
                played_cards.push(format!("{} (fetched)", basic.name()));
                state.battlefield.push(basic);
                state.library.shuffle(&mut thread_rng());
            }
            // Fetch goes to graveyard
            state.graveyard.push(land);
        } else {
            played_cards.push(land.name().to_string());
            state.battlefield.push(land);
        }
        state.lands_played += 1;
    }

    let mut mana = state.generate_mana();
    let mana_available = mana.total();
    let mut cards_cast = 0;
    let mut cards_drawn = 0;

    // Main phase: play cards in priority order
    loop {
        let mut played_anything = false;

        // 1. Play ramp artifacts first
        for i in (0..state.hand.len()).rev() {
            if let Card::Ramp { generic, .. } = &state.hand[i] {
                if mana.spend(*generic as u32, &[]) {
                    let card = state.hand.remove(i);
                    played_cards.push(card.name().to_string());
                    cards_drawn += card.draw_count();
                    state.battlefield.push(card);
                    cards_cast += 1;
                    played_anything = true;
                    break;
                }
            }
        }
        if played_anything { continue; }

        // 2. Try to cast commander (with tax)
        if let Some(cmd) = &state.commander {
            if let Card::Commander { generic, pips, name, .. } = cmd {
                let tax = state.commander_casts * 2;
                let total_generic = *generic as u32 + tax;
                
                // Ensure we actually have mana available
                if mana.total() > 0 && mana.spend(total_generic, pips) {
                    played_cards.push(format!("{} (cmdr tax: {})", name, tax));
                    let commander_card = state.commander.take().unwrap();
                    state.battlefield.push(commander_card);
                    state.commander_casts += 1;
                    cards_cast += 1;
                    played_anything = true;
                }
            }
        }
        if played_anything { continue; }

        // 3. Cast spells (prioritize card draw)
        let mut best_spell: Option<usize> = None;
        let mut best_has_draw = false;
        
        for i in 0..state.hand.len() {
            if let Card::Spell { generic, pips, .. } = &state.hand[i] {
                if mana.can_pay(*generic as u32, pips) {
                    let has_draw = state.hand[i].has_draw();
                    if best_spell.is_none() || (has_draw && !best_has_draw) {
                        best_spell = Some(i);
                        best_has_draw = has_draw;
                    }
                }
            }
        }

        if let Some(i) = best_spell {
            if let Card::Spell { generic, pips, type_line, .. } = &state.hand[i] {
                let generic_val = *generic as u32;
                let pips_clone = pips.clone();
                let type_line_clone = type_line.clone();
                
                if mana.spend(generic_val, &pips_clone) {
                    let card = state.hand.remove(i);
                    played_cards.push(card.name().to_string());
                    cards_drawn += card.draw_count();
                    
                    // Permanents go to battlefield, instants/sorceries to graveyard
                    let type_lower = type_line_clone.to_lowercase();
                    let is_instant_sorcery = type_lower.contains("instant") || type_lower.contains("sorcery");
                    
                    if is_instant_sorcery {
                        state.graveyard.push(card);
                    } else {
                        state.battlefield.push(card);
                    }
                    
                    cards_cast += 1;
                    played_anything = true;
                }
            }
        }

        if !played_anything {
            break;
        }
    }

    // Draw cards from effects
    state.draw(cards_drawn);

    let mana_spent = mana_available - mana.total();

    // Cleanup phase
    state.discard_to_hand_size(7);

    (mana_available, mana_spent, cards_cast, played_cards)
}

fn classify_turn(cards_cast: usize, leftover_mana: u32, hand_land_ratio: f64) -> &'static str {
    if cards_cast == 0 && hand_land_ratio >= 0.8 {
        "flood"  // All lands, can't cast
    } else if cards_cast == 0 {
        "screw"  // Have spells but no mana
    } else if leftover_mana >= 4 {
        "flood"  // Wasting significant mana
    } else {
        "ok"
    }
}

pub fn run(deck_file: &DeckFile, sims: usize, turns: usize) -> Stats {
    let deck = deck_file.expand();
    let commander = deck_file.commander();

    let examples = Mutex::new(Vec::new());

    let results: Vec<Vec<(u32, u32, u32, u32, u32, usize, usize)>> = (0..sims)
        .into_par_iter()
        .map(|sim_idx| {
            let mut state = GameState::new(deck.clone(), commander.clone());
            let mut turn_data = Vec::new();
            let mut snapshots = Vec::new();
            let capture = sim_idx < 5;

            for turn in 0..turns {
                let (mana_available, mana_spent, cards_cast, played_cards) = play_turn(&mut state, turn);
                let leftover = mana_available - mana_spent;
                
                let land_count = state.hand.iter().filter(|c| matches!(c, Card::Land { .. })).count();
                let hand_land_ratio = if state.hand.is_empty() { 0.0 } else { land_count as f64 / state.hand.len() as f64 };
                
                let status = classify_turn(cards_cast, leftover, hand_land_ratio);
                
                let (screw, flood, ok) = match status {
                    "screw" => (1, 0, 0),
                    "flood" => (0, 1, 0),
                    _ => (0, 0, 1),
                };

                if capture {
                    snapshots.push(TurnSnapshot {
                        turn: turn + 1,
                        hand: state.hand.iter().map(|c| c.name().to_string()).collect(),
                        battlefield: state.battlefield.iter().map(|c| c.name().to_string()).collect(),
                        played_cards,
                        mana_available,
                        mana_spent,
                        cards_cast,
                        status: status.to_string(),
                    });
                }

                turn_data.push((screw, flood, ok, mana_available, mana_spent, cards_cast, state.hand.len()));
            }

            if capture {
                let status_counts: HashMap<String, usize> = snapshots.iter()
                    .fold(HashMap::new(), |mut acc, s| {
                        *acc.entry(s.status.clone()).or_insert(0) += 1;
                        acc
                    });
                let final_status = status_counts.iter()
                    .max_by_key(|(_, &count)| count)
                    .map(|(s, _)| s.clone())
                    .unwrap_or_else(|| "ok".to_string());

                examples.lock().unwrap().push(GameTrace {
                    final_status,
                    turns: snapshots,
                });
            }

            turn_data
        })
        .collect();

    let mut stats = Stats::new(turns);

    for t in 0..turns {
        let mut s = 0;
        let mut f = 0;
        let mut o = 0;
        let mut total_avail = 0u32;
        let mut total_spent = 0u32;
        let mut total_cast = 0usize;
        let mut total_hand = 0usize;

        for r in &results {
            let (rs, rf, ro, avail, spent, cast, hand) = r[t];
            s += rs;
            f += rf;
            o += ro;
            total_avail += avail;
            total_spent += spent;
            total_cast += cast;
            total_hand += hand;
        }

        let n = sims as f64;
        stats.screw[t] = s as f64 / n;
        stats.flood[t] = f as f64 / n;
        stats.ok[t] = o as f64 / n;
        stats.avg_mana_available[t] = total_avail as f64 / n;
        stats.avg_mana_spent[t] = total_spent as f64 / n;
        stats.avg_cards_cast[t] = total_cast as f64 / n;
        stats.avg_hand_size[t] = total_hand as f64 / n;
    }

    stats.example_traces = examples.into_inner().unwrap();
    stats
}
