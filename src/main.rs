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
    #[arg(short, long, default_value = "12")]
    turns: usize,

    /// Output JSON file (optional)
    #[arg(short, long)]
    output: Option<PathBuf>,

    /// Print example game traces
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

    println!("Commander: {}", deck.name);
    println!("Running {} simulations over {} turns...", args.sims, args.turns);
    let start = std::time::Instant::now();
    let stats = run(&deck, args.sims, args.turns);
    let elapsed = start.elapsed();

    println!("\nCompleted in {:.2}s\n", elapsed.as_secs_f64());

    println!("=== Mana Analysis ===");
    
    // Calculate overall statistics
    let avg_screw = stats.screw.iter().sum::<f64>() / stats.screw.len() as f64;
    let avg_flood = stats.flood.iter().sum::<f64>() / stats.flood.len() as f64;
    let avg_ok = stats.ok.iter().sum::<f64>() / stats.ok.len() as f64;
    let avg_cards_cast = stats.avg_cards_cast.iter().sum::<f64>() / stats.avg_cards_cast.len() as f64;
    let avg_mana_avail = stats.avg_mana_available.iter().sum::<f64>() / stats.avg_mana_available.len() as f64;
    let avg_mana_spent = stats.avg_mana_spent.iter().sum::<f64>() / stats.avg_mana_spent.len() as f64;
    let efficiency = if avg_mana_avail > 0.0 { avg_mana_spent / avg_mana_avail * 100.0 } else { 0.0 };

    println!("Screw Rate:  {:.1}%", avg_screw * 100.0);
    println!("Flood Rate:  {:.1}%", avg_flood * 100.0);
    println!("Normal Rate: {:.1}%", avg_ok * 100.0);
    println!("\nAverage cards cast per turn: {:.2}", avg_cards_cast);
    println!("Mana efficiency: {:.1}%", efficiency);

    // Print example traces if verbose
    if args.verbose && !stats.example_traces.is_empty() {
        println!("\n=== Example Game Traces ===\n");
        for (i, trace) in stats.example_traces.iter().enumerate() {
            println!("Game {} - Final Status: {}", i + 1, trace.final_status);
            for snap in &trace.turns {
                println!("  Turn {}: {} cards cast, {}/{} mana, {} cards in hand [{}]",
                    snap.turn, snap.cards_cast, snap.mana_spent, snap.mana_available,
                    snap.hand.len(), snap.status);
                if !snap.played_cards.is_empty() {
                    println!("    Played: {}", snap.played_cards.join(", "));
                }
                if !snap.hand.is_empty() {
                    println!("    Hand: {}", snap.hand.join(", "));
                }
            }
            println!();
        }
    }
    
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
        println!("Output written to: {}", output_path.display());
    }
}
