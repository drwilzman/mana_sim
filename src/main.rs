use clap::Parser;
use std::path::PathBuf;

mod deck;
mod mana;
mod sim;
mod stats;

use deck::DeckFile;
use sim::run;

#[derive(Parser)]
#[command(name = "mana_sim")]
#[command(about = "MTG Commander mana simulation", long_about = None)]
struct Args {
    /// Deck JSON file path
    #[arg(short, long)]
    deck: PathBuf,

    /// Number of simulations to run
    #[arg(short, long, default_value = "50000")]
    sims: usize,

    /// Number of turns to simulate
    #[arg(short, long, default_value = "20")]
    turns: usize,

    /// Output JSON file (optional)
    #[arg(short, long)]
    output: Option<PathBuf>,

    /// Print detailed statistics
    #[arg(short, long)]
    verbose: bool,
}

fn main() {
    let args = Args::parse();

    println!("Loading deck: {}", args.deck.display());
    let file = std::fs::File::open(&args.deck)
        .unwrap_or_else(|e| panic!("Failed to open deck file: {}", e));
    
    let deck: DeckFile = serde_json::from_reader(file)
        .unwrap_or_else(|e| panic!("Failed to parse deck JSON: {}", e));

    println!("Running {} simulations over {} turns...", args.sims, args.turns);
    let start = std::time::Instant::now();
    let stats = run(&deck, args.sims, args.turns);
    let elapsed = start.elapsed();

    println!("\nCompleted in {:.2}s\n", elapsed.as_secs_f64());

    println!("=== Mana Analysis ===");
    
    if let Some(output_path) = args.output {
        let json = serde_json::json!({
            "screw": stats.screw,
            "flood": stats.flood,
            "ok": stats.ok,
            "avg_mana_spent": stats.avg_mana_spent,
            "avg_mana_available": stats.avg_mana_available,
            "avg_cards_cast": stats.avg_cards_cast,
            "avg_hand_size": stats.avg_hand_size,
            "example_traces": stats.example_traces
        });
        
        std::fs::write(&output_path, serde_json::to_string_pretty(&json).unwrap())
            .unwrap_or_else(|e| panic!("Failed to write output: {}", e));
    }
}
