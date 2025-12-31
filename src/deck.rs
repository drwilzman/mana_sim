use serde::Deserialize;

#[derive(Debug, Deserialize, Clone)]
#[serde(tag = "type")]
pub enum Card {
    Commander { generic: u8, pips: Vec<String>, count: u8 },
    Spell { generic: u8, pips: Vec<String>, count: u8 },
    Land { produces: Vec<String>, count: u8 },
    Ramp { generic: u8, produces: Vec<String>, count: u8 },
    Fetch { generic: u8, fetches: Vec<String>, count: u8 },
}

#[derive(Debug, Deserialize)]
pub struct DeckFile {
    pub name: String,
    pub cards: Vec<Card>,
}

impl DeckFile {
    /// Expands counts into actual Vec<Card> (flatten)
    pub fn expand(&self) -> Vec<Card> {
        let mut deck = Vec::new();
        for c in &self.cards {
            let n = match c {
                Card::Spell { count, .. } => *count,
                Card::Land { count, .. } => *count,
                Card::Ramp { count, .. } => *count,
                Card::Fetch { count, .. } => *count,
                Card::Commander { .. } => continue,
            };
            for _ in 0..n {
                deck.push(c.clone());
            }
        }
        assert_eq!(deck.len(), 99, "Deck must have 99 cards excluding commander");
        deck
    }

    /// Finds the commander (assumes exactly one in cards)
    pub fn commander(&self) -> Card {
        self.cards
            .iter()
            .find(|c| matches!(c, Card::Commander { .. }))
            .expect("Commander card not found in deck")
            .clone()
    }
}
