use crate::deck::Card;
use std::collections::HashMap;

/// Returns total generic + colored mana required for a set of cards
pub fn hand_cost(hand: &[Card]) -> (u32, HashMap<String, u32>) {
    let mut generic = 0;
    let mut colored = HashMap::new();

    for card in hand {
        match card {
            Card::Spell { generic: g, pips, .. } => {
                generic += *g as u32;
                for color in pips {
                    *colored.entry(color.clone()).or_insert(0) += 1;
                }
            }
            Card::Ramp { generic: g, .. } => {
                generic += *g as u32;
            }
            _ => {}
        }
    }

    (generic, colored)
}
