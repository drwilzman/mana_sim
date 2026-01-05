use serde::Deserialize;

#[derive(Debug, Deserialize, Clone)]
pub struct Feature {
    pub feature: String,
    pub costs: Vec<String>,
    pub timing: Vec<String>,
}

#[derive(Debug, Deserialize, Clone)]
#[serde(tag = "type")]
pub enum Card {
    Commander {
        name: String,
        generic: u8,
        pips: Vec<String>,
        features: Vec<Feature>,
    },
    Spell {
        name: String,
        generic: u8,
        pips: Vec<String>,
        features: Vec<Feature>,
        type_line: String,
        count: u8,
    },
    Land {
        name: String,
        produces: Vec<String>,
        is_fetch: bool,
        fetches: Vec<String>,
        count: u8,
    },
    Ramp {
        name: String,
        generic: u8,
        produces: Vec<String>,
        features: Vec<Feature>,
        count: u8,
    },
}

impl Card {
    pub fn has_draw(&self) -> bool {
        match self {
            Card::Spell { features, .. } | 
            Card::Ramp { features, .. } | 
            Card::Commander { features, .. } => {
                features.iter().any(|f| f.feature == "DRAW")
            }
            _ => false,
        }
    }

    pub fn draw_count(&self) -> usize {
        // Simple heuristic: each DRAW feature = 1 card
        match self {
            Card::Spell { features, .. } | 
            Card::Ramp { features, .. } | 
            Card::Commander { features, .. } => {
                features.iter().filter(|f| f.feature == "DRAW").count()
            }
            _ => 0,
        }
    }

    pub fn name(&self) -> &str {
        match self {
            Card::Commander { name, .. } => name,
            Card::Spell { name, .. } => name,
            Card::Land { name, .. } => name,
            Card::Ramp { name, .. } => name,
        }
    }
}

#[derive(Debug, Deserialize)]
pub struct DeckFile {
    pub name: String,
    pub cards: Vec<Card>,
}

impl DeckFile {
    pub fn expand(&self) -> Vec<Card> {
        let mut deck = Vec::new();
        for c in &self.cards {
            let n = match c {
                Card::Spell { count, .. } => *count,
                Card::Land { count, .. } => *count,
                Card::Ramp { count, .. } => *count,
                Card::Commander { .. } => continue,
            };
            for _ in 0..n {
                deck.push(c.clone());
            }
        }
        assert_eq!(deck.len(), 99, "Deck must have 99 cards excluding commander");
        deck
    }

    pub fn commander(&self) -> Card {
        self.cards
            .iter()
            .find(|c| matches!(c, Card::Commander { .. }))
            .expect("Commander card not found in deck")
            .clone()
    }

    pub fn basic_lands(&self) -> Vec<Card> {
        self.cards
            .iter()
            .filter(|c| matches!(c, Card::Land { is_fetch: false, .. }))
            .cloned()
            .collect()
    }
}
