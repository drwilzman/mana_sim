use crate::deck::{Card, DeckFile};
use crate::stats::Stats;
use rand::seq::SliceRandom;
use rand::thread_rng;
use rayon::prelude::*;
use std::collections::HashMap;

/// Mana pool with all colors and generic
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

    fn can_pay(&self, generic: u32, pips: &[String]) -> bool {
        // Count required pips per color
        let mut required_colors: HashMap<String, u32> = HashMap::new();
        for p in pips {
            *required_colors.entry(p.clone()).or_insert(0) += 1;
        }
        
        // Check we have enough of each color
        for (color, needed) in &required_colors {
            if self.colors.get(color).copied().unwrap_or(0) < *needed {
                return false;
            }
        }
        
        // Calculate total available mana after colored requirements
        let mut remaining_mana = self.generic;
        for (color, count) in &self.colors {
            let used = required_colors.get(color).copied().unwrap_or(0);
            remaining_mana += count.saturating_sub(used);
        }
        
        remaining_mana >= generic
    }

    fn spend_safe(&mut self, generic: u32, pips: &[String]) -> bool {
        if !self.can_pay(generic, pips) {
            return false;
        }
        
        // Count and pay colored pips
        let mut pip_counts: HashMap<String, u32> = HashMap::new();
        for p in pips {
            *pip_counts.entry(p.clone()).or_insert(0) += 1;
        }
        
        for (color, count) in pip_counts {
            *self.colors.get_mut(&color).unwrap() -= count;
        }
        
        // Pay generic cost with remaining mana
        let mut remaining = generic;
        
        // Use generic mana first
        let from_generic = remaining.min(self.generic);
        self.generic -= from_generic;
        remaining -= from_generic;
        
        // Use colored mana for generic cost if needed
        if remaining > 0 {
            for color_count in self.colors.values_mut() {
                if remaining == 0 {
                    break;
                }
                let from_color = remaining.min(*color_count);
                *color_count -= from_color;
                remaining -= from_color;
            }
        }
        
        true
    }
}

/// Attempts to cast cards, returns true if any card was cast
/// add power, toughness, etc output for tracking how we're doing
/// eg. a lot of artifact equipments = no actual damage
/// but a lot of little creatures is a lot of power. add some counters, equipment, etc... it increases,
/// how do we track that? or at least attempt to? 
fn play_cards(hand: &mut Vec<Card>, mana: &mut ManaPool, commander: &mut Option<Card>) -> bool {
    let mut cast_any = false;

    loop {
        let mut played = false;

        // Cast ramp/fetch first (they produce mana)
        for i in (0..hand.len()).rev() {
            match &hand[i] {
                Card::Ramp { generic, produces, .. } => {
                    if mana.spend_safe(*generic as u32, &[]) {
                        for c in produces {
                            if c == "C" {
                                mana.generic += 1;
                            } else {
                                mana.add_color(c, 1);
                            }
                        }
                        hand.remove(i);
                        cast_any = true;
                        played = true;
                    }
                }
                Card::Fetch { generic, fetches, .. } => {
                    if mana.spend_safe(*generic as u32, &[]) {
                        for c in fetches {
                            if c == "C" {
                                mana.generic += 1;
                            } else {
                                mana.add_color(c, 1);
                            }
                        }
                        hand.remove(i);
                        cast_any = true;
                        played = true;
                    }
                }
                _ => {}
            }
        }

        // Cast spells
        for i in (0..hand.len()).rev() {
            if let Card::Spell { generic, pips, .. } = &hand[i] {
                if mana.spend_safe(*generic as u32, pips) {
                    hand.remove(i);
                    cast_any = true;
                    played = true;
                }
            }
        }

        // Cast commander if possible
        if let Some(cmd) = commander {
            if let Card::Commander { generic, pips, .. } = cmd {
                if mana.spend_safe(*generic as u32, pips) {
                    *commander = None;
                    cast_any = true;
                    played = true;
                }
            }
        }

        if !played {
            break;
        }
    }

    cast_any
}

pub fn run(deck_file: &DeckFile, sims: usize, turns: usize) -> Stats {
    let deck = deck_file.expand();
    let commander_card = deck_file.commander();

    let results: Vec<Vec<(u32, u32, u32)>> = (0..sims)
        .into_par_iter()
        .map(|_| {
            let mut rng = thread_rng();
            let mut draw_deck = deck.clone();
            draw_deck.shuffle(&mut rng);

            let mut hand: Vec<Card> = Vec::new();
            let mut battlefield: Vec<Card> = Vec::new();
            let mut commander = Some(commander_card.clone());

            let mut screw = vec![0u32; turns];
            let mut flood = vec![0u32; turns];
            let mut ok = vec![0u32; turns];

            for turn in 0..turns {
                // Draw cards
                if turn == 0 {
                    for _ in 0..7 {
                        hand.push(draw_deck.pop().unwrap());
                    }
                    
                    // Mulligan logic: keep if 2-5 lands
                    let land_count = hand.iter().filter(|c| matches!(c, Card::Land { .. })).count();
                    if land_count < 2 || land_count > 5 {
                        draw_deck.extend(hand.drain(..));
                        draw_deck.shuffle(&mut rng);
                        for _ in 0..7 {
                            hand.push(draw_deck.pop().unwrap());
                        }
                    }
                } else if let Some(c) = draw_deck.pop() {
                    hand.push(c);
                }

                // Play one land automatically
                if let Some(pos) = hand.iter().position(|c| matches!(c, Card::Land { .. })) {
                    battlefield.push(hand.remove(pos));
                }

                // Build mana pool from lands only
                let mut mana = ManaPool::new();
                for l in &battlefield {
                    if let Card::Land { produces, .. } = l {
                        for c in produces {
                            if c == "C" {
                                mana.generic += 1;
                            } else {
                                mana.add_color(c, 1);
                            }
                        }
                    }
                }

                // Play cards, add power, toughness, creatures, etc stats counter to track play performance
                let cast_any = play_cards(&mut hand, &mut mana, &mut commander);

                // Calculate total leftover mana
                let leftover_mana = mana.generic + mana.colors.values().sum::<u32>();

                // Classify turn
                if !cast_any {
                    screw[turn] += 1;
                } else if leftover_mana >= 2 {
                    flood[turn] += 1;
                } else {
                    ok[turn] += 1;
                }
            }

            screw.into_iter()
                .zip(flood)
                .zip(ok)
                .map(|((s, f), o)| (s, f, o))
                .collect()
        })
        .collect();

    // Aggregate results
    let mut screw = vec![0.0; turns];
    let mut flood = vec![0.0; turns];
    let mut ok = vec![0.0; turns];

    for t in 0..turns {
        let mut s = 0;
        let mut f = 0;
        let mut o = 0;
        for r in &results {
            let (rs, rf, ro) = r[t];
            s += rs;
            f += rf;
            o += ro;
        }
        let n = sims as f64;
        screw[t] = s as f64 / n;
        flood[t] = f as f64 / n;
        ok[t] = o as f64 / n;
    }

    Stats { screw, flood, ok }
}
