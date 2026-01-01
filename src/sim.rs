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

    fn spend_safe(&mut self, generic: u32, pips: &[String]) -> bool {
        if !self.can_pay(generic, pips) {
            return false;
        }
        
        let mut pip_counts: HashMap<String, u32> = HashMap::new();
        for p in pips {
            *pip_counts.entry(p.clone()).or_insert(0) += 1;
        }
        
        for (color, count) in pip_counts {
            *self.colors.get_mut(&color).unwrap() -= count;
        }
        
        let mut remaining = generic;
        let from_generic = remaining.min(self.generic);
        self.generic -= from_generic;
        remaining -= from_generic;
        
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

fn card_name(c: &Card) -> String {
    match c {
        Card::Commander { .. } => "Commander".to_string(),
        Card::Spell { .. } => "Spell".to_string(),
        Card::Land { produces, .. } => format!("Land({})", produces.join("")),
        Card::Ramp { .. } => "Ramp".to_string(),
        Card::Fetch { .. } => "Fetch".to_string(),
    }
}

fn play_cards(hand: &mut Vec<Card>, battlefield: &mut Vec<Card>, mana: &mut ManaPool, commander: &mut Option<Card>) -> usize {
    let mut cast_count = 0;

    loop {
        let mut played = false;

        // Try to cast and play ramp artifacts (they go to battlefield)
        for i in (0..hand.len()).rev() {
            if let Card::Ramp { generic, .. } = &hand[i] {
                if mana.spend_safe(*generic as u32, &[]) {
                    battlefield.push(hand.remove(i));
                    cast_count += 1;
                    played = true;
                }
            }
        }

        // Try to cast fetch (one-time effect, produces mana immediately)
        for i in (0..hand.len()).rev() {
            if let Card::Fetch { generic, fetches, .. } = &hand[i] {
                if mana.spend_safe(*generic as u32, &[]) {
                    for c in fetches {
                        if c == "C" {
                            mana.generic += 1;
                        } else {
                            mana.add_color(c, 1);
                        }
                    }
                    hand.remove(i);
                    cast_count += 1;
                    played = true;
                }
            }
        }

        // Try to cast spells
        for i in (0..hand.len()).rev() {
            if let Card::Spell { generic, pips, .. } = &hand[i] {
                if mana.spend_safe(*generic as u32, pips) {
                    hand.remove(i);
                    cast_count += 1;
                    played = true;
                }
            }
        }

        // Try to cast commander
        if let Some(cmd) = commander {
            if let Card::Commander { generic, pips, .. } = cmd {
                if mana.spend_safe(*generic as u32, pips) {
                    *commander = None;
                    cast_count += 1;
                    played = true;
                }
            }
        }

        if !played { break; }
    }

    cast_count
}

pub fn run(deck_file: &DeckFile, sims: usize, turns: usize) -> Stats {
    let deck = deck_file.expand();
    let commander_card = deck_file.commander();

    let examples = Mutex::new(Vec::new());

    let results: Vec<Vec<(u32, u32, u32, u32, u32, usize, usize)>> = (0..sims)
        .into_par_iter()
        .map(|sim_idx| {
            let mut rng = thread_rng();
            let mut draw_deck = deck.clone();
            draw_deck.shuffle(&mut rng);

            let mut hand: Vec<Card> = Vec::new();
            let mut battlefield: Vec<Card> = Vec::new();
            let mut commander = Some(commander_card.clone());

            let mut turn_data = Vec::new();
            let mut snapshots = Vec::new();
            let capture = sim_idx < 5;

            for turn in 0..turns {
                if turn == 0 {
                    for _ in 0..7 {
                        hand.push(draw_deck.pop().unwrap());
                    }
                    
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

                // Play one land per turn
                if let Some(pos) = hand.iter().position(|c| matches!(c, Card::Land { .. })) {
                    battlefield.push(hand.remove(pos));
                }

                // Generate mana from all lands and ramp artifacts on battlefield
                let mut mana = ManaPool::new();
                for permanent in &battlefield {
                    match permanent {
                        Card::Land { produces, .. } => {
                            if produces.is_empty() {
                                // Edge case: land produces nothing (shouldn't happen)
                                continue;
                            } else if produces.len() > 1 {
                                // Multi-color land: produces 1 generic that can pay for anything
                                mana.generic += 1;
                            } else {
                                // Single color land
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

                let mana_available = mana.total();
                let cards_cast = play_cards(&mut hand, &mut battlefield, &mut mana, &mut commander);
                let mana_spent = mana_available - mana.total();
                let leftover_mana = mana.total();
                
                // Discard down to 7 at end of turn
                while hand.len() > 7 {
                    hand.pop();
                }
                
                let hand_size = hand.len();

                let land_count = hand.iter().filter(|c| matches!(c, Card::Land { .. })).count();
                let _nonland_count = hand.len() - land_count;

                let (screw, flood, ok) = if cards_cast == 0 && land_count >= hand.len() - 1 {
                    (0, 1, 0)  // flood: hand is all/mostly lands
                } else if cards_cast == 0 {
                    (1, 0, 0)  // screw: have spells but can't cast them
                } else if leftover_mana >= 3 {
                    (0, 1, 0)  // flood: cast stuff but wasted 3+ mana
                } else {
                    (0, 0, 1)  // ok
                };

                let status = if screw == 1 { "screw" } else if flood == 1 { "flood" } else { "ok" };

                if capture {
                    snapshots.push(TurnSnapshot {
                        turn: turn + 1,
                        hand: hand.iter().map(card_name).collect(),
                        battlefield: battlefield.iter().map(card_name).collect(),
                        mana_available,
                        mana_spent,
                        cards_cast,
                        status: status.to_string(),
                    });
                }

                turn_data.push((screw, flood, ok, mana_available, mana_spent, cards_cast, hand_size));
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
