import mana_sim
import matplotlib.pyplot as plt
import argparse
import time
from pathlib import Path
from datetime import datetime

def main():
    parser = argparse.ArgumentParser(description='Run EDH mana simulation')
    parser.add_argument('--deck', type=str, required=True, help='Deck name (without path/extension)')
    parser.add_argument('--sims', type=int, default=50000, help='Number of simulations')
    parser.add_argument('--turns', type=int, default=20, help='Number of turns to simulate')
    parser.add_argument('--flood-margin', type=int, default=2, help='Mana threshold for flood')
    parser.add_argument('--title', type=str, default=None, help='Graph title')
    parser.add_argument('--output-dir', type=str, default='output', help='Output directory')
    
    args = parser.parse_args()
    
    deck_path = f"decks/{args.deck}.json"
    title = args.title or f"{args.deck.title()} Deck Analysis"
    
    output_dir = Path(args.output_dir)
    output_dir.mkdir(exist_ok=True)
    
    start = time.time()
    stats = mana_sim.run_sim(
        deck_path=deck_path,
        sims=args.sims,
        turns=args.turns,
        flood_margin=args.flood_margin
    )
    elapsed = time.time() - start
    print(f"Elapsed: {elapsed:.2f}s")
    
    screw = stats.screw
    flood = stats.flood
    ok = stats.ok
    turns = list(range(1, len(screw) + 1))
    
    # Better styling
    plt.style.use('seaborn-v0_8-darkgrid')
    fig, ax = plt.subplots(figsize=(10, 6))
    
    ax.plot(turns, screw, marker='o', linewidth=2.5, markersize=8, 
            color='#e74c3c', label='Mana Screwed', alpha=0.9)
    ax.plot(turns, flood, marker='s', linewidth=2.5, markersize=8,
            color='#3498db', label='Mana Flooded', alpha=0.9)
    ax.plot(turns, ok, marker='^', linewidth=2.5, markersize=8,
            color='#2ecc71', label='Goldilocks', alpha=0.9)
    
    ax.set_title(title, fontsize=16, fontweight='bold', pad=20)
    ax.set_xlabel('Turn', fontsize=13, fontweight='semibold')
    ax.set_ylabel('Fraction of Games', fontsize=13, fontweight='semibold')
    ax.set_xticks(turns)
    ax.set_ylim(0, 1)
    ax.axhline(y=0.5, color='gray', linestyle=':', linewidth=1.5, alpha=0.6, label='50%')
    ax.grid(alpha=0.4, linestyle='--', linewidth=0.7)
    ax.legend(loc='best', fontsize=11, framealpha=0.95)
    
    plt.tight_layout()
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    if args.title is None:
        output_path = output_dir / f"mana_simulation_{timestamp}.png"
    else:
        output_path = output_dir / f"mana_simulation_{args.title}.png"
    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    plt.close()
    print(f"Graph saved to {output_path}")

if __name__ == '__main__':
    main()
