"""
Deck Simulation Module - Integrates Rust mana simulator with Python deck encoder
"""
import json
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime

try:
    import matplotlib.pyplot as plt
    import numpy as np
    HAS_PLOTTING = True
except ImportError:
    HAS_PLOTTING = False

try:
    import mana_sim
    HAS_SIM = True
except ImportError:
    HAS_SIM = False


@dataclass
class SimulationResults:
    """Container for simulation results"""
    screw_rate: float
    flood_rate: float
    ok_rate: float
    avg_cards_cast: float
    avg_mana_efficiency: float
    avg_hand_size: float
    turn_data: Dict[str, List[float]]
    example_traces: List[Dict]
    
    def summary(self) -> str:
        """Generate text summary"""
        return (
            f"Simulation Results:\n"
            f"  Screw Rate: {self.screw_rate*100:.1f}%\n"
            f"  Flood Rate: {self.flood_rate*100:.1f}%\n"
            f"  Normal Rate: {self.ok_rate*100:.1f}%\n"
            f"  Avg Cards Cast/Turn: {self.avg_cards_cast:.2f}\n"
            f"  Mana Efficiency: {self.avg_mana_efficiency*100:.1f}%\n"
            f"  Avg Hand Size: {self.avg_hand_size:.1f}"
        )


class DeckSimulator:
    """Handles deck simulation and analysis"""
    
    @staticmethod
    def sanitize_filename(name: str) -> str:
        """Remove invalid filename characters"""
        # Remove slashes, commas, apostrophes, other special chars
        safe = re.sub(r'[/\\:*?"<>|,\']', '', name)
        # Replace spaces with underscores
        safe = safe.replace(' ', '_')
        # Remove multiple consecutive underscores
        safe = re.sub(r'_+', '_', safe)
        return safe.strip('_')
    
    @staticmethod
    def parse_mana_cost(mana_cost: str) -> Tuple[int, List[str]]:
        """Parse mana cost string like '{2}{W}{B}' -> (generic, pips)"""
        if not mana_cost:
            return (0, [])
        
        generic = 0
        pips = []
        tokens = re.findall(r'\{([^}]+)\}', mana_cost)
        
        for token in tokens:
            token = token.upper()  # Normalize to uppercase
            if token.isdigit():
                generic += int(token)
            elif token == 'X':
                generic += 0  # X is variable, treat as 0 for now
            elif token in ['W', 'U', 'B', 'R', 'G', 'C']:
                pips.append(token)
            elif '/' in token:  # Hybrid mana like W/B
                # Take first color
                first_color = token.split('/')[0]
                if first_color in ['W', 'U', 'B', 'R', 'G', 'C']:
                    pips.append(first_color)
        
        return (generic, pips)
    
    @staticmethod
    def extract_land_production(card: Dict) -> List[str]:
        """Determine mana production from land"""
        oracle = card.get('oracle_text', '').upper()
        type_line = card.get('type_line', '').lower()
        produces = []
        
        # Basic land types
        basics = {
            'plains': 'W', 'island': 'U', 'swamp': 'B',
            'mountain': 'R', 'forest': 'G'
        }
        
        for basic, color in basics.items():
            if basic in type_line:
                produces.append(color)
        
        # Explicit mana symbols
        if not produces:
            for c in ['W', 'U', 'B', 'R', 'G']:
                if f'{{{c}}}' in oracle:
                    produces.append(c)
        
        if '{C}' in oracle or 'COLORLESS' in oracle:
            produces.append('C')
        
        return produces if produces else ['C']
    
    @staticmethod
    def is_fetch_land(card: Dict) -> Tuple[bool, List[str]]:
        """Check if land is fetch and what it fetches"""
        oracle = card.get('oracle_text', '').lower()
        
        if 'search your library' not in oracle:
            return (False, [])
        
        fetches = []
        if 'plains' in oracle:
            fetches.append('W')
        if 'island' in oracle:
            fetches.append('U')
        if 'swamp' in oracle:
            fetches.append('B')
        if 'mountain' in oracle:
            fetches.append('R')
        if 'forest' in oracle:
            fetches.append('G')
        
        return (len(fetches) > 0, fetches)
    
    @staticmethod
    def convert_to_sim_format(deck_model: Dict) -> Dict:
        """Convert encoded deck to Rust simulator format"""
        sim_cards = []
        
        # Commander
        cmd = deck_model['commander']
        generic, pips = DeckSimulator.parse_mana_cost(cmd['mana_cost'])
        sim_cards.append({
            'type': 'Commander',
            'name': cmd['name'],
            'generic': generic,
            'pips': pips,
            'features': cmd['features']
        })
        
        # Aggregate cards
        land_groups: Dict[Tuple, Tuple[List[str], int]] = {}
        spell_groups: Dict[Tuple, Tuple[List[str], int]] = {}
        ramp_groups: Dict[Tuple, Tuple[List[str], int]] = {}
        
        for card in deck_model['cards']:
            if card['is_land']:
                is_fetch, fetches = DeckSimulator.is_fetch_land(card)
                produces = DeckSimulator.extract_land_production(card)
                
                if is_fetch:
                    sim_cards.append({
                        'type': 'Land',
                        'name': card['name'],
                        'produces': produces,
                        'is_fetch': True,
                        'fetches': fetches,
                        'count': 1
                    })
                else:
                    key = tuple(sorted(produces))
                    if key not in land_groups:
                        land_groups[key] = ([], 0)
                    names, count = land_groups[key]
                    names.append(card['name'])
                    land_groups[key] = (names, count + 1)
            else:
                generic, pips = DeckSimulator.parse_mana_cost(card['mana_cost'])
                is_mana_rock = any(f['feature'] == 'MANA_ROCK' for f in card['features'])
                
                if is_mana_rock:
                    oracle = card.get('oracle_text', '').upper()
                    produces = []
                    for c in ['W', 'U', 'B', 'R', 'G', 'C']:
                        if f'{{{c}}}' in oracle:
                            produces.append(c)
                    if not produces:
                        produces = ['C']
                    
                    key = (generic, tuple(sorted(produces)))
                    if key not in ramp_groups:
                        ramp_groups[key] = ([], 0)
                    names, count = ramp_groups[key]
                    names.append(card['name'])
                    ramp_groups[key] = (names, count + 1)
                else:
                    key = (generic, tuple(sorted(pips)))
                    if key not in spell_groups:
                        spell_groups[key] = ([], 0)
                    names, count = spell_groups[key]
                    names.append(card['name'])
                    spell_groups[key] = (names, count + 1)
        
        # Add lands
        for produces, (names, count) in land_groups.items():
            sim_cards.append({
                'type': 'Land',
                'name': names[0],
                'produces': list(produces),
                'is_fetch': False,
                'fetches': [],
                'count': count
            })
        
        # Add ramp
        for (generic, produces), (names, count) in ramp_groups.items():
            features = next((c['features'] for c in deck_model['cards'] if c['name'] in names), [])
            sim_cards.append({
                'type': 'Ramp',
                'name': names[0],
                'generic': generic,
                'produces': list(produces),
                'features': features,
                'count': count
            })
        
        # Add spells
        for (generic, pips), (names, count) in spell_groups.items():
            # Find the first card with this name to get features and type_line
            sample_card = None
            for card in deck_model['cards']:
                if card['name'] in names:
                    sample_card = card
                    break
            
            if sample_card:
                features = sample_card.get('features', [])
                type_line = sample_card.get('type_line', 'Unknown')
            else:
                features = []
                type_line = 'Unknown'
                print(f"Warning: Could not find card data for spell group: {names}")
            
            sim_cards.append({
                'type': 'Spell',
                'name': names[0] if names else 'Unknown',
                'generic': generic,
                'pips': list(pips),
                'features': features,
                'type_line': type_line,
                'count': count
            })
        
        sim_deck = {
            'name': cmd['name'],
            'cards': sim_cards
        }
        
        # Validate all Spell cards have type_line
        for card in sim_cards:
            if card.get('type') == 'Spell' and 'type_line' not in card:
                print(f"ERROR: Spell card missing type_line: {card.get('name', 'Unknown')}")
                card['type_line'] = 'Unknown'
        
        return sim_deck
    
    @staticmethod
    def run_simulation(
        deck_model: Dict,
        sims: int = 10000,
        turns: int = 12,
        output_dir: Optional[Path] = None,
        deck_name: Optional[str] = None
    ) -> Optional[SimulationResults]:
        """Run simulation and return results"""
        if not HAS_SIM:
            print("Rust simulator not available. Install with: maturin develop --release")
            return None
        
        # Convert format
        sim_deck = DeckSimulator.convert_to_sim_format(deck_model)
        
        # Write temp file
        temp_path = Path("_temp_sim_deck.json")
        if temp_path.exists():
            temp_path.unlink()
        
        with open(temp_path, 'w') as f:
            json.dump(sim_deck, f, indent=2)
        
        try:
            # Run simulation
            print(f"Running {sims} simulations...")
            stats = mana_sim.run_sim(str(temp_path), sims, turns)
            
            # Calculate aggregates
            screw = stats.screw
            flood = stats.flood
            ok = stats.ok
            mana_avail = stats.avg_mana_available
            mana_spent = stats.avg_mana_spent
            cards_cast = stats.avg_cards_cast
            hand_size = stats.avg_hand_size
            
            avg_screw = sum(screw) / len(screw)
            avg_flood = sum(flood) / len(flood)
            avg_ok = sum(ok) / len(ok)
            avg_cast = sum(cards_cast) / len(cards_cast)
            avg_hand = sum(hand_size) / len(hand_size)
            
            total_avail = sum(mana_avail)
            total_spent = sum(mana_spent)
            efficiency = total_spent / total_avail if total_avail > 0 else 0
            
            # Extract traces
            traces = []
            if hasattr(stats, 'example_traces'):
                for trace in stats.example_traces[:5]:
                    traces.append({
                        'final_status': trace.final_status,
                        'turns': [
                            {
                                'turn': t.turn,
                                'hand': list(t.hand),
                                'battlefield': list(t.battlefield),
                                'played_cards': list(t.played_cards),
                                'mana_available': t.mana_available,
                                'mana_spent': t.mana_spent,
                                'cards_cast': t.cards_cast,
                                'status': t.status
                            }
                            for t in trace.turns
                        ]
                    })
            
            results = SimulationResults(
                screw_rate=avg_screw,
                flood_rate=avg_flood,
                ok_rate=avg_ok,
                avg_cards_cast=avg_cast,
                avg_mana_efficiency=efficiency,
                avg_hand_size=avg_hand,
                turn_data={
                    'screw': list(screw),
                    'flood': list(flood),
                    'ok': list(ok),
                    'mana_available': list(mana_avail),
                    'mana_spent': list(mana_spent),
                    'cards_cast': list(cards_cast),
                    'hand_size': list(hand_size)
                },
                example_traces=traces
            )
            
            # Save results
            if output_dir:
                if deck_name:
                    base_name = deck_name
                else:
                    base_name = DeckSimulator.sanitize_filename(sim_deck['name'])
                output_path = output_dir / f"{base_name}_sim_results.json"
                with open(output_path, 'w') as f:
                    json.dump({
                        'summary': {
                            'screw_rate': avg_screw,
                            'flood_rate': avg_flood,
                            'ok_rate': avg_ok,
                            'avg_cards_cast': avg_cast,
                            'avg_mana_efficiency': efficiency
                        },
                        'turn_data': results.turn_data,
                        'example_traces': traces
                    }, f, indent=2)
            
            return results
            
        finally:
            temp_path.unlink(missing_ok=True)
    
    @staticmethod
    def generate_report(
        results: SimulationResults,
        deck_model: Dict,
        sims: int,
        turns: int,
        output_path: Path
    ):
        """Generate comprehensive simulation report"""
        commander_name = deck_model['commander']['name']
        # Keep original name for display in report
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        # Calculate additional metrics
        classification = DeckSimulator.classify_deck_by_simulation(results)
        
        # Early vs late game
        early_screw = sum(results.turn_data['screw'][:4]) / 4
        early_flood = sum(results.turn_data['flood'][:4]) / 4
        late_screw = sum(results.turn_data['screw'][8:]) / len(results.turn_data['screw'][8:]) if len(results.turn_data['screw']) > 8 else 0
        late_flood = sum(results.turn_data['flood'][8:]) / len(results.turn_data['flood'][8:]) if len(results.turn_data['flood']) > 8 else 0
        
        # Peak performance
        best_turn_cast = max(results.turn_data['cards_cast'])
        best_turn_idx = results.turn_data['cards_cast'].index(best_turn_cast) + 1
        
        report = f"""
{'='*80}
SIMULATION REPORT - {commander_name}
{'='*80}
Generated: {timestamp}
Simulations: {sims:,} games | Turns Analyzed: {turns}

{'='*80}
OVERALL PERFORMANCE
{'='*80}

Game State Distribution:
  Mana Screw:  {results.screw_rate*100:6.2f}%  (Unable to cast spells)
  Mana Flood:  {results.flood_rate*100:6.2f}%  (Excess mana wasted)
  Normal:      {results.ok_rate*100:6.2f}%  (Efficient gameplay)

Gameplay Metrics:
  Average Cards Cast per Turn:     {results.avg_cards_cast:.2f}
  Average Mana Efficiency:         {results.avg_mana_efficiency*100:.1f}%
  Average Hand Size:               {results.avg_hand_size:.1f} cards

Deck Classification:
  Consistency Rating:  {classification['consistency']}
  Speed Rating:        {classification['speed']}

{'='*80}
TEMPORAL ANALYSIS
{'='*80}

Early Game (Turns 1-4):
  Screw Rate:  {early_screw*100:.1f}%
  Flood Rate:  {early_flood*100:.1f}%

Late Game (Turn 9+):
  Screw Rate:  {late_screw*100:.1f}%
  Flood Rate:  {late_flood*100:.1f}%

Peak Performance:
  Best Turn: Turn {best_turn_idx} ({best_turn_cast:.2f} cards cast on average)

{'='*80}
TURN-BY-TURN BREAKDOWN
{'='*80}

Turn | Screw | Flood | Normal | Avg Cast | Mana Avail | Mana Spent | Efficiency
-----|-------|-------|--------|----------|------------|------------|------------
"""
        
        for i in range(min(turns, len(results.turn_data['screw']))):
            screw_pct = results.turn_data['screw'][i] * 100
            flood_pct = results.turn_data['flood'][i] * 100
            ok_pct = results.turn_data['ok'][i] * 100
            cast = results.turn_data['cards_cast'][i]
            avail = results.turn_data['mana_available'][i]
            spent = results.turn_data['mana_spent'][i]
            eff = (spent / avail * 100) if avail > 0 else 0
            
            report += f" {i+1:2d}  | {screw_pct:5.1f} | {flood_pct:5.1f} | {ok_pct:6.1f} | {cast:8.2f} | {avail:10.1f} | {spent:10.1f} | {eff:9.1f}%\n"
        
        # Issues and recommendations
        report += f"\n{'='*80}\n"
        report += "ANALYSIS & RECOMMENDATIONS\n"
        report += f"{'='*80}\n\n"
        
        if classification['issues']:
            report += "Issues Detected:\n"
            for issue in classification['issues']:
                report += f"  - {issue}\n"
        else:
            report += "No major issues detected. Deck shows solid performance.\n"
        
        # Specific recommendations
        report += "\nRecommendations:\n"
        if results.screw_rate > 0.25:
            report += "  - Increase land count by 1-2 or add more 0-2 CMC ramp\n"
        if results.flood_rate > 0.30:
            report += "  - Reduce land count by 1-2 or add more card draw\n"
        if results.avg_mana_efficiency < 0.70:
            report += "  - Adjust mana curve to better match land progression\n"
        if results.avg_cards_cast < 1.5:
            report += "  - Lower average CMC or add more fast mana\n"
        if early_screw > 0.30:
            report += "  - Critical early game issues - prioritize low-cost cards\n"
        if late_flood > 0.35:
            report += "  - Add mana sinks or card draw to use excess late-game mana\n"
        
        # Example traces
        report += f"\n{'='*80}\n"
        report += "EXAMPLE GAME TRACES\n"
        report += f"{'='*80}\n\n"
        
        for i, trace in enumerate(results.example_traces[:3]):
            report += f"Game {i+1} - Final Status: {trace['final_status'].upper()}\n"
            report += "-" * 80 + "\n"
            
            for turn in trace['turns'][:8]:
                report += f"\nTurn {turn['turn']}: {turn['status'].upper()}\n"
                report += f"  Cast: {turn['cards_cast']} cards | "
                report += f"Mana: {turn['mana_spent']}/{turn['mana_available']} | "
                report += f"Hand: {len(turn['hand'])} cards\n"
                
                if turn['played_cards']:
                    played = ', '.join(turn['played_cards'])
                    report += f"  Played: {played}\n"
                
                if turn['hand']:
                    hand_preview = ', '.join(turn['hand'][:5])
                    if len(turn['hand']) > 5:
                        hand_preview += f", ... +{len(turn['hand'])-5} more"
                    report += f"  Hand: {hand_preview}\n"
                
                if turn['battlefield']:
                    bf_count = len(turn['battlefield'])
                    report += f"  Battlefield: {bf_count} permanents\n"
            
            report += "\n"
        
        report += f"{'='*80}\n"
        report += "END OF REPORT\n"
        report += f"{'='*80}\n"
        
        # Write report
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(report)
    
    @staticmethod
    def plot_simulation_results(
        results: SimulationResults,
        deck_model: Dict,
        output_path: Optional[Path] = None
    ):
        """Generate simulation visualizations with embedded report"""
        if not HAS_PLOTTING:
            print("Plotting not available (matplotlib not installed)")
            return
        
        plt.style.use('dark_background')
        fig = plt.figure(figsize=(24, 14))
        gs = fig.add_gridspec(3, 3, hspace=0.35, wspace=0.3)
        
        turns = list(range(1, len(results.turn_data['screw']) + 1))
        commander_name = deck_model['commander']['name']
        
        # 1. Screw/Flood/OK rates over time
        ax1 = fig.add_subplot(gs[0, :2])
        ax1.plot(turns, [x*100 for x in results.turn_data['screw']], 
                label='Screw', color='#ff3b30', linewidth=2.5)
        ax1.plot(turns, [x*100 for x in results.turn_data['flood']], 
                label='Flood', color='#0a84ff', linewidth=2.5)
        ax1.plot(turns, [x*100 for x in results.turn_data['ok']], 
                label='Normal', color='#ffd60a', linewidth=2.5)
        ax1.set_xlabel('Turn', fontsize=12, fontweight='bold')
        ax1.set_ylabel('Probability (%)', fontsize=12, fontweight='bold')
        ax1.set_title(f'Game State Distribution - {commander_name}', fontsize=14, fontweight='bold')
        ax1.legend(fontsize=11, loc='upper left')
        ax1.grid(alpha=0.3)
        
        # 2. Summary pie chart
        ax2 = fig.add_subplot(gs[0, 2])
        colors = ['#ff6b6b', '#4ecdc4', '#95e1d3']
        wedges, texts, autotexts = ax2.pie(
            [results.screw_rate*100, results.flood_rate*100, results.ok_rate*100],
            labels=['Screw', 'Flood', 'Normal'],
            autopct='%1.1f%%',
            colors=colors,
            startangle=90,
            textprops={'fontsize': 11, 'fontweight': 'bold'}
        )
        ax2.set_title('Overall Distribution', fontsize=13, fontweight='bold')
        
        # 3. Cards cast per turn
        ax3 = fig.add_subplot(gs[1, 0])
        ax3.plot(turns, results.turn_data['cards_cast'], 
                color='#f9ca24', linewidth=2.5, marker='o', markersize=4)
        ax3.set_xlabel('Turn', fontsize=12, fontweight='bold')
        ax3.set_ylabel('Cards Cast', fontsize=12, fontweight='bold')
        ax3.set_title('Cards Cast Per Turn', fontsize=13, fontweight='bold')
        ax3.grid(alpha=0.3)
        ax3.axhline(y=results.avg_cards_cast, color='white', linestyle='--', 
                   alpha=0.5, label=f'Avg: {results.avg_cards_cast:.2f}')
        ax3.legend(fontsize=9)
        
        # 4. Mana efficiency
        ax4 = fig.add_subplot(gs[1, 1])
        ax4.plot(turns, results.turn_data['mana_available'], 
                label='Available', color='#95e1d3', linewidth=2.5)
        ax4.plot(turns, results.turn_data['mana_spent'], 
                label='Spent', color='#4ecdc4', linewidth=2.5)
        ax4.fill_between(turns, results.turn_data['mana_spent'], 
                         results.turn_data['mana_available'], 
                         alpha=0.2, color='#ff6b6b', label='Wasted')
        ax4.set_xlabel('Turn', fontsize=12, fontweight='bold')
        ax4.set_ylabel('Mana', fontsize=12, fontweight='bold')
        ax4.set_title('Mana Usage', fontsize=13, fontweight='bold')
        ax4.legend(fontsize=10)
        ax4.grid(alpha=0.3)
        
        # 5. Hand size
        ax5 = fig.add_subplot(gs[1, 2])
        ax5.plot(turns, results.turn_data['hand_size'], 
                color='#ff9ff3', linewidth=2.5)
        ax5.axhline(y=7, color='#ffffff', linestyle='--', alpha=0.5, label='Max (7)')
        ax5.set_xlabel('Turn', fontsize=12, fontweight='bold')
        ax5.set_ylabel('Cards in Hand', fontsize=12, fontweight='bold')
        ax5.set_title('Average Hand Size', fontsize=13, fontweight='bold')
        ax5.legend(fontsize=10)
        ax5.grid(alpha=0.3)
        
        # 6. Performance summary text box
        ax6 = fig.add_subplot(gs[2, :])
        ax6.axis('off')
        
        classification = DeckSimulator.classify_deck_by_simulation(results)
        
        summary_text = f"""
SIMULATION SUMMARY

Overall Performance:
  • Consistency: {classification['consistency']}
  • Speed: {classification['speed']}
  • Screw Rate: {results.screw_rate*100:.1f}%  |  Flood Rate: {results.flood_rate*100:.1f}%  |  Normal: {results.ok_rate*100:.1f}%
  • Avg Cards Cast/Turn: {results.avg_cards_cast:.2f}  |  Mana Efficiency: {results.avg_mana_efficiency*100:.1f}%

Early Game (Turns 1-4):
  • Screw: {sum(results.turn_data['screw'][:4])/4*100:.1f}%  |  Flood: {sum(results.turn_data['flood'][:4])/4*100:.1f}%

Mid Game (Turns 5-8):
  • Avg Cast: {sum(results.turn_data['cards_cast'][4:8])/4:.2f} cards/turn
  • Avg Mana: {sum(results.turn_data['mana_available'][4:8])/4:.1f} available, {sum(results.turn_data['mana_spent'][4:8])/4:.1f} spent

Late Game (Turn 9+):
  • Screw: {sum(results.turn_data['screw'][8:])/len(results.turn_data['screw'][8:])*100 if len(results.turn_data['screw']) > 8 else 0:.1f}%  |  Flood: {sum(results.turn_data['flood'][8:])/len(results.turn_data['flood'][8:])*100 if len(results.turn_data['flood']) > 8 else 0:.1f}%
"""
        
        if classification['issues']:
            summary_text += "\nIssues Detected:\n"
            for issue in classification['issues']:
                summary_text += f"  • {issue}\n"
        else:
            summary_text += "\nNo major issues detected.\n"
        
        ax6.text(0.5, 0.5, summary_text, transform=ax6.transAxes,
                fontsize=11, verticalalignment='center', horizontalalignment='center',
                family='monospace', color='white',
                bbox=dict(boxstyle='round', facecolor='#2a2a2a', alpha=0.9, pad=1))
        
        if output_path:
            plt.savefig(output_path, dpi=300, bbox_inches='tight', facecolor='#1a1a1a')
        
        plt.close()
    
    @staticmethod
    def classify_deck_by_simulation(results: SimulationResults) -> Dict:
        """Classify deck performance based on simulation"""
        classification = {
            'consistency': 'Unknown',
            'speed': 'Unknown',
            'issues': []
        }
        
        # Consistency
        if results.screw_rate < 0.15 and results.flood_rate < 0.20:
            classification['consistency'] = 'Excellent'
        elif results.screw_rate < 0.25 and results.flood_rate < 0.30:
            classification['consistency'] = 'Good'
        elif results.screw_rate < 0.35 or results.flood_rate < 0.40:
            classification['consistency'] = 'Average'
        else:
            classification['consistency'] = 'Poor'
        
        # Speed
        if results.avg_cards_cast >= 2.0:
            classification['speed'] = 'Fast'
        elif results.avg_cards_cast >= 1.5:
            classification['speed'] = 'Medium'
        else:
            classification['speed'] = 'Slow'
        
        # Issues
        if results.screw_rate > 0.30:
            classification['issues'].append('High screw rate - consider more lands or ramp')
        if results.flood_rate > 0.35:
            classification['issues'].append('High flood rate - too many lands or need more card draw')
        if results.avg_mana_efficiency < 0.65:
            classification['issues'].append('Low mana efficiency - mana curve issues')
        if results.avg_cards_cast < 1.2:
            classification['issues'].append('Low cast rate - curve too high or mana issues')
        
        return classification
