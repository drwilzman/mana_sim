"""
EDH Deck Encoder - Production-ready deck ingestion and card encoding system
"""
import json
import re
import sys
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import List, Dict, Set, Optional, Tuple
from urllib.request import urlopen, Request
from urllib.error import URLError
from collections import Counter
import math
from math import comb

OUTPUT_DIR = Path("output")
DECKS_DIR = Path("decks")
OUTPUT_DIR.mkdir(exist_ok=True)
DECKS_DIR.mkdir(exist_ok=True)

try:
    import matplotlib.pyplot as plt
    import seaborn as sns
    import numpy as np
    HAS_PLOTTING = True
except ImportError:
    HAS_PLOTTING = False

#skryfall api
CACHE_FILE = "oracle-cards.json"
SCRYFALL_BULK_URL = "https://api.scryfall.com/bulk-data/oracle-cards"

@dataclass
class CardRecord:
    """Raw Scryfall card data"""
    name: str
    cmc: float
    type_line: str
    color_identity: List[str]
    oracle_text: str = ""
    mana_cost: str = ""
    layout: str = "normal"    
    
@dataclass
class FeatureExtraction:
    """Mechanical features with costs and timing"""
    feature: str
    costs: List[str] = field(default_factory=list)
    timing: List[str] = field(default_factory=list)
    

@dataclass
class EncodedCard:
    """Processed card with mechanical analysis"""
    name: str
    cmc: float
    type_line: str
    color_identity: List[str]
    oracle_text: str
    mana_cost: str
    is_land: bool
    layout: str  # ADD THIS LINE
    features: List[Dict] = field(default_factory=list)
    

@dataclass
class DeckModel:
    """Complete deck with commander, cards, and statistics"""
    commander: EncodedCard
    cards: List[EncodedCard]
    illegal_cards: List[str]
    statistics: Dict = field(default_factory=dict)


class ScryfallCache:
    """Manages local Scryfall card cache"""
    
    def __init__(self, cache_path: str = CACHE_FILE):
        self.cache_path = Path(cache_path)
        self.cards: Dict[str, CardRecord] = {}
        
    def load_or_fetch(self) -> None:
        """Load cache or fetch from Scryfall"""
        if self.cache_path.exists():
            print(f"Loading cache from {self.cache_path}")
            with open(self.cache_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                for card_data in data:
                    name = card_data['name'].lower()
                    layout = card_data.get('layout', 'normal')
                    # Handle double-faced cards - get mana cost from first face
                    mana_cost = card_data.get('mana_cost', '')
                    if not mana_cost and 'card_faces' in card_data:
                        mana_cost = card_data['card_faces'][0].get('mana_cost', '')
                    
                    self.cards[name] = CardRecord(
                        name=card_data['name'],
                        cmc=card_data.get('cmc', 0),
                        type_line=card_data.get('type_line', ''),
                        color_identity=card_data.get('color_identity', []),
                        oracle_text=card_data.get('oracle_text', ''),
                        mana_cost=mana_cost,
                        layout=layout
                    )
            print(f"Loaded {len(self.cards)} cards from cache")
        else:
            print("Cache not found, fetching from Scryfall...")
            self._fetch_and_save()
    
    def _fetch_and_save(self) -> None:
        """Fetch bulk data from Scryfall and save to cache"""
        try:
            req = Request(SCRYFALL_BULK_URL, headers={'User-Agent': 'EDH-Deck-Encoder/1.0'})
            with urlopen(req) as response:
                bulk_info = json.loads(response.read())
            
            download_uri = bulk_info['download_uri']
            print(f"Downloading bulk data from {download_uri}")
            
            req = Request(download_uri, headers={'User-Agent': 'EDH-Deck-Encoder/1.0'})
            with urlopen(req) as response:
                cards_data = json.loads(response.read())
            
            print(f"Fetched {len(cards_data)} cards")
            
            with open(self.cache_path, 'w', encoding='utf-8') as f:
                json.dump(cards_data, f)
            
            for card_data in cards_data:
                name = card_data['name'].lower()
                
                # Handle double-faced cards - get mana cost from first face
                mana_cost = card_data.get('mana_cost', '')
                if not mana_cost and 'card_faces' in card_data:
                    mana_cost = card_data['card_faces'][0].get('mana_cost', '')
                layout = card_data.get('layout', 'normal')
                self.cards[name] = CardRecord(
                    name=card_data['name'],
                    cmc=card_data.get('cmc', 0),
                    type_line=card_data.get('type_line', ''),
                    color_identity=card_data.get('color_identity', []),
                    oracle_text=card_data.get('oracle_text', ''),
                    mana_cost=mana_cost,
                    layout=layout
                )
        except URLError as e:
            print(f"Error fetching from Scryfall: {e}")
            sys.exit(1)
    
    def find_card(self, name: str) -> Optional[CardRecord]:
        """Find exact card match"""
        return self.cards.get(name.lower())
    
    def find_partial(self, partial: str) -> List[CardRecord]:
        """Find cards matching partial name"""
        partial_lower = partial.lower()
        matches = [card for name, card in self.cards.items() if partial_lower in name]
        return matches


class MechanicsExtractor:
    """Extract mechanical features from oracle text - Modular and maintainable"""
    
    @staticmethod
    def extract_features(card: CardRecord) -> List[FeatureExtraction]:
        """Extract all features with costs and timing"""
        text = card.oracle_text.lower()
        type_line = card.type_line.lower()
        features = []
        
        # Run all detectors
        detectors = [
            MechanicsExtractor._detect_mana_production,
            MechanicsExtractor._detect_card_draw,
            MechanicsExtractor._detect_ramp,
            MechanicsExtractor._detect_removal,
            MechanicsExtractor._detect_tokens,
            MechanicsExtractor._detect_lifegain,
            MechanicsExtractor._detect_lifeloss,
            MechanicsExtractor._detect_sacrifice,
            MechanicsExtractor._detect_death_triggers,
            MechanicsExtractor._detect_counters,
            MechanicsExtractor._detect_tribal,
        ]
        
        for detector in detectors:
            detected = detector(text, type_line)
            if detected:
                if isinstance(detected, list):
                    features.extend(detected)
                else:
                    features.append(detected)
        
        return features
    
    # ============================================================================
    # MANA PRODUCTION
    # ============================================================================
    
    @staticmethod
    def _detect_mana_production(text: str, type_line: str) -> Optional[FeatureExtraction]:
        """Detect mana-producing effects (rocks, rituals, dorks)"""
        
        # Mana rocks (artifacts with "{T}: Add...")
        if 'artifact' in type_line and re.search(r'\{t\}:?\s*add\s+\{[wubrgc]', text):
            return FeatureExtraction('MANA_ROCK', [], [])
        
        # Ritual effects (instants/sorceries that add mana)
        if ('instant' in type_line or 'sorcery' in type_line) and re.search(r'add\s+\{[wubrgc]+\}', text):
            # Count mana symbols to determine power
            mana_match = re.findall(r'add\s+(\{[wubrgc]+\}+)', text)
            if mana_match:
                # Example: "Add {B}{B}{B}" -> MANA_SPELL_3
                mana_count = len(re.findall(r'\{[wubrgc]\}', mana_match[0], re.IGNORECASE))
                timing = ['INSTANT'] if 'instant' in type_line else ['SORCERY']
                return FeatureExtraction(f'MANA_SPELL_{mana_count}', [], timing)
        
        # Mana dorks (creatures that tap for mana)
        if 'creature' in type_line and re.search(r'\{t\}:?\s*add', text):
            return FeatureExtraction('MANA_DORK', [], [])
        
        return None
    
    # ============================================================================
    # CARD ADVANTAGE
    # ============================================================================
    
    @staticmethod
    def _detect_card_draw(text: str, type_line: str) -> Optional[FeatureExtraction]:
        """Detect card draw effects"""
        patterns = [
            r'\bdraw\s+(?:a|one|two|three|four|x)\s+card',
            r'\bdraw\s+cards?\b',
            r'\byou\s+draw\b',
        ]
        
        if any(re.search(p, text) for p in patterns):
            costs, timing = MechanicsExtractor._analyze_activation(text, 'draw')
            return FeatureExtraction('DRAW', costs, timing)
        
        return None
    
    # ============================================================================
    # RAMP & LAND FETCH
    # ============================================================================
    
    @staticmethod
    def _detect_ramp(text: str, type_line: str) -> Optional[FeatureExtraction]:
        """Detect land ramp effects"""
        patterns = [
            r'search.*library.*(land|plains|island|swamp|mountain|forest)',
            r'put.*land.*(?:onto the battlefield|into play)',
            r'you may play an additional land',
        ]
        
        if any(re.search(p, text) for p in patterns):
            costs, timing = MechanicsExtractor._analyze_activation(text, 'search|land')
            return FeatureExtraction('RAMP', costs, timing)
        
        return None
    
    # ============================================================================
    # REMOVAL & INTERACTION
    # ============================================================================
    
    @staticmethod
    def _detect_removal(text: str, type_line: str) -> Optional[List[FeatureExtraction]]:
        """Detect removal effects"""
        features = []
        
        # Board wipes (destroy/exile all)
        board_wipe_patterns = [
            r'destroy all (?:creatures|nonland permanents|permanents)',
            r'exile all (?:creatures|nonland permanents|permanents)',
            r'all creatures.*(?:get -\d+/-\d+|die)',
            r'each creature gets -\d+/-\d+',
        ]
        
        if any(re.search(p, text) for p in board_wipe_patterns):
            costs, timing = MechanicsExtractor._analyze_activation(text, 'destroy|exile|all')
            features.append(FeatureExtraction('BOARD_WIPE', costs, timing))
        
        # Spot removal (destroy/exile target)
        spot_removal_patterns = [
            r'destroy target (?:creature|permanent|artifact|enchantment)',
            r'exile target (?:creature|permanent|artifact|enchantment)',
            r'target (?:creature|permanent).*gets? -\d+/-\d+',
        ]
        
        if any(re.search(p, text) for p in spot_removal_patterns):
            costs, timing = MechanicsExtractor._analyze_activation(text, 'destroy|exile|target')
            features.append(FeatureExtraction('REMOVAL', costs, timing))
        
        return features if features else None
    
    @staticmethod
    def _detect_counters(text: str, type_line: str) -> Optional[FeatureExtraction]:
        """Detect counterspells"""
        if re.search(r'counter\s+target\s+(?:spell|activated|triggered)', text):
            costs, timing = MechanicsExtractor._analyze_activation(text, 'counter')
            return FeatureExtraction('COUNTER', costs, timing)
        return None
    
    # ============================================================================
    # TOKEN GENERATION
    # ============================================================================
    
    @staticmethod
    def _detect_tokens(text: str, type_line: str) -> Optional[FeatureExtraction]:
        """Detect token creation"""
        if re.search(r'create.+(?:token|creature token)', text):
            costs, timing = MechanicsExtractor._analyze_activation(text, 'create')
            return FeatureExtraction('TOKEN', costs, timing)
        return None
    
    # ============================================================================
    # LIFE MANIPULATION
    # ============================================================================
    
    @staticmethod
    def _detect_lifegain(text: str, type_line: str) -> Optional[FeatureExtraction]:
        """Detect life gain effects"""
        patterns = [
            r'\bgain\s+\d*\s*life\b',
            r'\byou gain\b.*\blife\b',
            r'\blifelink\b',
        ]
        
        if any(re.search(p, text) for p in patterns):
            costs, timing = MechanicsExtractor._analyze_activation(text, 'gain|lifelink')
            return FeatureExtraction('LIFE_GAIN', costs, timing)
        return None
    
    @staticmethod
    def _detect_lifeloss(text: str, type_line: str) -> Optional[FeatureExtraction]:
        """Detect life loss effects"""
        patterns = [
            r'(?:each opponent|target (?:player|opponent)).*loses?\s+\d*\s*life',
            r'pay\s+\d*\s*life',
            r'lose\s+\d*\s*life',
        ]
        
        if any(re.search(p, text) for p in patterns):
            costs, timing = MechanicsExtractor._analyze_activation(text, 'lose|pay')
            return FeatureExtraction('LIFE_LOSS', costs, timing)
        return None
    
    # ============================================================================
    # SACRIFICE & DEATH
    # ============================================================================
    
    @staticmethod
    def _detect_sacrifice(text: str, type_line: str) -> Optional[FeatureExtraction]:
        """Detect sacrifice effects"""
        if not re.search(r'\bsacrific', text):
            return None
        
        costs, timing = MechanicsExtractor._analyze_activation(text, 'sacrifice')
        
        # Determine what's being sacrificed
        sac_types = []
        if re.search(r'sacrifice.*creature', text):
            sac_types.append('CREATURE')
        if re.search(r'sacrifice.*artifact', text):
            sac_types.append('ARTIFACT')
        if re.search(r'sacrifice.*permanent', text):
            sac_types.append('PERMANENT')
        
        feature_name = 'SAC_' + '_'.join(sac_types) if sac_types else 'SAC'
        return FeatureExtraction(feature_name, costs, timing)
    
    @staticmethod
    def _detect_death_triggers(text: str, type_line: str) -> Optional[FeatureExtraction]:
        """Detect death/dies triggers"""
        patterns = [
            r'\bwhen.*dies\b',
            r'\bwhenever.*dies\b',
            r'\bwhen.*is put into.*graveyard\b',
        ]
        
        if any(re.search(p, text) for p in patterns):
            return FeatureExtraction('DEATH_TRIGGER', [], ['TRIGGERED', 'ON_DEATH'])
        return None
    
    # ============================================================================
    # TRIBAL
    # ============================================================================
    
    @staticmethod
    def _detect_tribal(text: str, type_line: str) -> Optional[List[FeatureExtraction]]:
        """Detect tribal synergies"""
        features = []
        
        tribes = [
            'vampire', 'zombie', 'elf', 'goblin', 'merfolk', 
            'dragon', 'angel', 'demon', 'soldier', 'wizard',
            'cleric', 'warrior', 'rogue', 'shaman'
        ]
        
        for tribe in tribes:
            # Check both oracle text and type line
            if tribe in text or tribe in type_line:
                features.append(FeatureExtraction(f'TRIBAL_{tribe.upper()}', [], []))
        
        return features if features else None
    
    # ============================================================================
    # COST & TIMING ANALYSIS
    # ============================================================================
    
    @staticmethod
    def _analyze_activation(text: str, effect_keyword: str) -> Tuple[List[str], List[str]]:
        """Analyze costs and timing for an effect"""
        costs = []
        timing = []
        
        # Check for activated ability pattern
        # Format: "{costs}: Effect"
        activated_pattern = r'\{[^}]*\}[^:]*:\s*(?:' + effect_keyword + r')'
        if re.search(activated_pattern, text):
            timing.append('ACTIVATED')
            
            # Extract all cost components before the colon
            cost_section = re.search(r'([^.]*\{[^}]*\}[^:]*):.*(?:' + effect_keyword + r')', text)
            if cost_section:
                cost_text = cost_section.group(1)
                
                # Check specific cost types
                if re.search(r'\{[0-9xX]+\}', cost_text):
                    costs.append('MANA')
                if re.search(r'\{t\}', cost_text):
                    costs.append('TAP')
                if re.search(r'pay.*life', cost_text):
                    costs.append('LIFE')
                if re.search(r'sacrifice', cost_text):
                    costs.append('SAC')
                if re.search(r'discard', cost_text):
                    costs.append('DISCARD')
        
        # Check for triggered abilities
        trigger_patterns = [
            r'when.*(?:' + effect_keyword + r')',
            r'whenever.*(?:' + effect_keyword + r')',
            r'at the beginning.*(?:' + effect_keyword + r')',
        ]
        if any(re.search(p, text) for p in trigger_patterns):
            timing.append('TRIGGERED')
            
            if re.search(r'enters(?:\s+the\s+battlefield)?', text):
                timing.append('ETB')
            if re.search(r'at the beginning', text):
                timing.append('UPKEEP')
        
        # Check spell timing restrictions
        if not timing:  # Only for spells without activated/triggered timing
            if 'instant' in text:
                timing.append('INSTANT')
            elif 'sorcery' in text:
                timing.append('SORCERY')
        
        return costs, timing


class DeckParser:
    """Parse EDH decklist files"""

    @staticmethod
    def parse_decklist(file_path: str) -> List[Tuple[str, int]]:
        """Parse decklist file and return (card_name, quantity) tuples.
        Stops reading at a line starting with 'maybe'.
        """
        cards = []
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"Decklist file not found: {file_path}")

        with open(path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#') or line.startswith('//'):
                    continue

                # Stop parsing at first line that starts with 'maybe'
                if line.lower().startswith('maybe'):
                    break

                # Skip lines that clearly aren't card entries
                if not re.match(r'^\d', line):
                    continue

                # Remove leading count (e.g., "1x Card Name" or "1 Card Name")
                match = re.match(r'^(\d+)x?\s+(.+)$', line)
                if match:
                    quantity = int(match.group(1))
                    card_name = match.group(2).strip()
                else:
                    quantity = 1
                    card_name = line.strip()

                if card_name:
                    cards.append((card_name, quantity))

        return cards



class EDHValidator:
    """Validate EDH deck legality"""
    
    @staticmethod
    def is_legal_in_identity(card: CardRecord, commander_identity: Set[str]) -> bool:
        """Check if card's color identity is subset of commander's"""
        card_identity = set(card.color_identity)
        return card_identity.issubset(commander_identity)


class DeckAnalytics:
    """Statistical analysis and visualization"""
    
    @staticmethod
    def hypergeometric(N: int, K: int, n: int, k: int) -> float:
        """Hypergeometric probability: P(X = k)"""
        def comb(n, r):
            if r > n or r < 0:
                return 0
            return math.factorial(n) // (math.factorial(r) * math.factorial(n - r))
        
        return comb(K, k) * comb(N - K, n - k) / comb(N, n)
    
    @staticmethod
    def opening_hand_land_prob(deck_size: int, land_count: int, hand_size: int = 7) -> Dict[int, float]:
        """Calculate probability of getting exactly k lands in opening hand"""
        probs = {}
        for k in range(hand_size + 1):
            probs[k] = DeckAnalytics.hypergeometric(deck_size, land_count, hand_size, k)
        return probs

    @staticmethod
    def mulligan_success(
        deck_size: int,
        land_count: int,
        fast_mana_count: int,
        min_sources: int = 3,
        max_lands: int = 5,
    ) -> Dict[str, float]:
        """Probability of a keepable hand at each mulligan size"""

        results = {}

        for hand_size in range(7, 3, -1):
            p = 0.0
            for l in range(0, min(hand_size, land_count) + 1):
                for f in range(0, min(hand_size - l, fast_mana_count) + 1):
                    total_sources = l + f
                    if total_sources < min_sources or l > max_lands:
                        continue

                    rest = hand_size - l - f
                    other = deck_size - land_count - fast_mana_count
                    if rest > other:
                        continue

                    p += (
                        comb(land_count, l)
                        * comb(fast_mana_count, f)
                        * comb(other, rest)
                        / comb(deck_size, hand_size)
                    )

            results[f"mull_to_{hand_size}"] = p

        return results

    
    @staticmethod
    def mulligan_distribution(deck_size: int, land_count: int, target_lands: int = 3) -> Dict[str, float]:
        """Calculate distribution of where you stop mulliganing"""
        # P(success at each hand size)
        p7 = sum(DeckAnalytics.hypergeometric(deck_size, land_count, 7, k) for k in range(target_lands, 8))
        p6 = sum(DeckAnalytics.hypergeometric(deck_size, land_count, 6, k) for k in range(target_lands, 7))
        p5 = sum(DeckAnalytics.hypergeometric(deck_size, land_count, 5, k) for k in range(target_lands, 6))
        p4 = sum(DeckAnalytics.hypergeometric(deck_size, land_count, 4, k) for k in range(target_lands, 5))
        
        # Distribution of stopping points
        stop_at_7 = p7
        stop_at_6 = (1 - p7) * p6
        stop_at_5 = (1 - p7) * (1 - p6) * p5
        must_go_4 = (1 - p7) * (1 - p6) * (1 - p5)
        
        return {
            'stop_7': stop_at_7,
            'stop_6': stop_at_6,
            'stop_5': stop_at_5,
            'stop_4': must_go_4
        }
    
    @staticmethod
    def free_mulligan_analysis(deck_size: int, land_count: int, min_lands: int, max_lands: int) -> Dict[str, float]:
        """Calculate success rate with London mulligan (1 free mulligan)"""
        # P(min_lands to max_lands in a 7-card hand)
        prob_good_hand = sum(
            DeckAnalytics.hypergeometric(deck_size, land_count, 7, k) 
            for k in range(min_lands, max_lands + 1)
        )
        
        # With free mulligan: 1 - P(both hands fail)
        prob_with_free_mull = 1 - (1 - prob_good_hand) ** 2
        
        return {
            'no_mulligan': prob_good_hand,
            'with_free_mulligan': prob_with_free_mull
        }
    
    @staticmethod
    def create_visualizations(deck_model: DeckModel, output_prefix: str = "deck_analysis"):
        """Generate dark mode analytics visualizations"""
        if not HAS_PLOTTING:
            print("Skipping visualizations - matplotlib/seaborn not installed")
            return
        
        # Set dark theme
        plt.style.use('dark_background')
        sns.set_palette("husl")
        
        # Extract data
        nonland_cards = [c for c in deck_model.cards if not c.is_land]
        land_cards = [c for c in deck_model.cards if c.is_land]
        
        cmc_counts = Counter([int(c.cmc) for c in nonland_cards])
        total_lands = len(land_cards)
        total_nonlands = len(nonland_cards)
        deck_size = total_lands + total_nonlands + 1  # +1 for commander
        
        # Create figure with subplots
        fig = plt.figure(figsize=(20, 14))
        gs = fig.add_gridspec(4, 2, hspace=0.35, wspace=0.3)
        
        # 1. Mana Curve
        ax1 = fig.add_subplot(gs[0, :])
        cmcs = sorted(cmc_counts.keys())
        counts = [cmc_counts[cmc] for cmc in cmcs]
        bars = ax1.bar(cmcs, counts, color='#00d9ff', edgecolor='white', linewidth=0.5)
        ax1.set_xlabel('Mana Value', fontsize=12, fontweight='bold')
        ax1.set_ylabel('Number of Cards', fontsize=12, fontweight='bold')
        ax1.set_title(f'Mana Curve - {deck_model.commander.name}', fontsize=14, fontweight='bold')
        ax1.grid(axis='y', alpha=0.3)
        
        # Add count labels on bars
        for bar in bars:
            height = bar.get_height()
            ax1.text(bar.get_x() + bar.get_width()/2., height,
                    f'{int(height)}', ha='center', va='bottom', fontsize=9)
        
        # 2. Opening Hand Land Probability
        ax2 = fig.add_subplot(gs[1, 0])
        hand_probs = DeckAnalytics.opening_hand_land_prob(deck_size, total_lands, 7)
        lands = list(hand_probs.keys())
        probs = [hand_probs[k] * 100 for k in lands]
        bars = ax2.bar(lands, probs, color='#ff6b6b', edgecolor='white', linewidth=0.5)
        ax2.set_xlabel('Number of Lands', fontsize=12, fontweight='bold')
        ax2.set_ylabel('Probability (%)', fontsize=12, fontweight='bold')
        ax2.set_title('Opening Hand (7 cards) - Land Distribution', fontsize=13, fontweight='bold')
        ax2.grid(axis='y', alpha=0.3)
        
        # Highlight 2-4 land range
        for i, bar in enumerate(bars):
            if 2 <= lands[i] <= 4:
                bar.set_color('#4ecdc4')
            height = bar.get_height()
            ax2.text(bar.get_x() + bar.get_width()/2., height,
                    f'{height:.1f}%', ha='center', va='bottom', fontsize=8)
        
        # 3. Free Mulligan Success (3-4 Lands)
        ax3 = fig.add_subplot(gs[1, 1])
        free_mull_3_4 = DeckAnalytics.free_mulligan_analysis(deck_size, total_lands, 3, 4)
        labels = ['No Mulligan', 'With Free Mulligan']
        probs_3_4 = [free_mull_3_4['no_mulligan'] * 100, free_mull_3_4['with_free_mulligan'] * 100]
        colors_fm = ['#ff6b6b', '#4ecdc4']
        bars = ax3.bar(labels, probs_3_4, color=colors_fm, edgecolor='white', linewidth=1)
        ax3.set_ylabel('Success Rate (%)', fontsize=12, fontweight='bold')
        ax3.set_title('Opening Hand Success (3-4 Lands)', fontsize=13, fontweight='bold')
        ax3.grid(axis='y', alpha=0.3)
        ax3.set_ylim(0, 100)
        
        for i, bar in enumerate(bars):
            height = bar.get_height()
            ax3.text(bar.get_x() + bar.get_width()/2., height,
                    f'{height:.1f}%', ha='center', va='bottom', fontsize=10, fontweight='bold')
        
        # 4. Mulligan Distribution (Where you stop) - PIE CHART
        ax4 = fig.add_subplot(gs[2, 0])
        mull_dist = DeckAnalytics.mulligan_distribution(deck_size, total_lands, 3)
        stop_labels = ['Keep 7', 'Mull to 6', 'Mull to 5', 'Mull to 4']
        stop_probs = [
            mull_dist['stop_7'] * 100,
            mull_dist['stop_6'] * 100,
            mull_dist['stop_5'] * 100,
            mull_dist['stop_4'] * 100
        ]
        colors_dist = ['#4ecdc4', '#95e1d3', '#f9ca24', '#ff6b6b']
        
        wedges, texts, autotexts = ax4.pie(
            stop_probs,
            labels=stop_labels,
            autopct='%1.1f%%',
            colors=colors_dist,
            startangle=90,
            textprops={'fontsize': 10, 'fontweight': 'bold'}
        )
        ax4.set_title('Mulligan Distribution (≥3 Lands Target)', fontsize=13, fontweight='bold')
        
        # 5. Feature Distribution
        ax5 = fig.add_subplot(gs[2, 1])
        feature_counts = deck_model.statistics.get('feature_counts', {})
        if feature_counts:
            sorted_features = sorted(feature_counts.items(), key=lambda x: x[1], reverse=True)[:10]
            features = [f[0] for f in sorted_features]
            counts = [f[1] for f in sorted_features]
            bars = ax5.barh(features, counts, color='#f38181', edgecolor='white', linewidth=0.5)
            ax5.set_xlabel('Count', fontsize=12, fontweight='bold')
            ax5.set_title('Top 10 Mechanical Features', fontsize=13, fontweight='bold')
            ax5.grid(axis='x', alpha=0.3)
            
            for i, bar in enumerate(bars):
                width = bar.get_width()
                ax5.text(width, bar.get_y() + bar.get_height()/2.,
                        f' {int(width)}', ha='left', va='center', fontsize=9)
        
        # 6. Power Level Breakdown
        ax6 = fig.add_subplot(gs[3, 0])
        power_level = deck_model.statistics.get('power_level', {})
        if power_level:
            components = power_level.get('components', {})
            comp_names = list(components.keys())
            comp_values = list(components.values())
            
            colors_power = ['#ff6b6b', '#4ecdc4', '#f9ca24', '#95e1d3', '#ff9ff3', '#45b7d1']
            bars = ax6.barh(comp_names, comp_values, color=colors_power, edgecolor='white', linewidth=1)
            ax6.set_xlabel('Power Contribution', fontsize=12, fontweight='bold')
            ax6.set_title(f"Power Level: {power_level.get('score', 0)}/10 (Raw: {power_level.get('raw_score', 0)})", 
                         fontsize=13, fontweight='bold')
            ax6.grid(axis='x', alpha=0.3)
            
            for i, bar in enumerate(bars):
                width = bar.get_width()
                ax6.text(width, bar.get_y() + bar.get_height()/2.,
                        f' {width:.1f}', ha='left', va='center', fontsize=9)
        
        # 7. Synergy & Efficiency Metrics
        ax7 = fig.add_subplot(gs[3, 1])
        
        power_level = deck_model.statistics.get('power_level', {})
        
        metrics = {
            'Fast Mana': power_level.get('fast_mana_count', 0),
            'Mana Rocks': deck_model.statistics.get('feature_counts', {}).get('MANA_ROCK', 0),
            'Land Ramp': deck_model.statistics.get('feature_counts', {}).get('RAMP', 0),
            'Card Draw': deck_model.statistics.get('feature_counts', {}).get('DRAW', 0),
            'Board Wipes': deck_model.statistics.get('feature_counts', {}).get('BOARD_WIPE', 0),
            'Spot Removal': deck_model.statistics.get('feature_counts', {}).get('REMOVAL', 0),
            'Counterspells': deck_model.statistics.get('feature_counts', {}).get('COUNTER', 0),
            'Low CMC (≤2)': int(power_level.get('efficiency_ratio', 0) * len(nonland_cards)),
            'X-Spells': deck_model.statistics.get('x_spell_count', 0),
            'Token Makers': deck_model.statistics.get('feature_counts', {}).get('TOKEN', 0),
            'Death Triggers': deck_model.statistics.get('feature_counts', {}).get('DEATH_TRIGGER', 0)
        }
        
        # Remove zero values
        metrics = {k: v for k, v in metrics.items() if v > 0}
        
        y_pos = np.arange(len(metrics))
        values = list(metrics.values())
        labels = list(metrics.keys())
        
        colors_metrics = ['#4ecdc4' if v >= 5 else '#f9ca24' if v >= 3 else '#ff6b6b' for v in values]
        bars = ax7.barh(y_pos, values, color=colors_metrics, edgecolor='white', linewidth=1)
        ax7.set_yticks(y_pos)
        ax7.set_yticklabels(labels)
        ax7.set_xlabel('Count', fontsize=12, fontweight='bold')
        ax7.set_title('Deck Construction Metrics', fontsize=13, fontweight='bold')
        ax7.grid(axis='x', alpha=0.3)
        
        for i, bar in enumerate(bars):
            width = bar.get_width()
            ax7.text(width, bar.get_y() + bar.get_height()/2.,
                    f' {int(width)}', ha='left', va='center', fontsize=9, fontweight='bold')
        
        # Add X-spell list if any
        x_spells = deck_model.statistics.get('x_spells', [])
        if x_spells:
            x_text = "X-Spells:\n" + "\n".join([f"• {name}" for name in x_spells[:6]])
            if len(x_spells) > 6:
                x_text += f"\n... +{len(x_spells) - 6} more"
            fig.text(0.73, 0.15, x_text, fontsize=8, va='top', ha='left', 
                    color='white', family='monospace',
                    bbox=dict(boxstyle='round', facecolor='#2a2a2a', alpha=0.8))
        
        # Summary stats text
        power_score = deck_model.statistics.get('power_level', {}).get('score', 0)
        x_count = deck_model.statistics.get('x_spell_count', 0)
        fig.text(0.5, 0.01, 
                f"Deck Size: {deck_size} | Lands: {total_lands} ({total_lands/deck_size*100:.1f}%) | Nonlands: {total_nonlands} | "
                f"Avg CMC: {sum(c.cmc for c in nonland_cards)/len(nonland_cards):.2f} | Power Level: {power_score}/10 | "
                f"X-Spells: {x_count} | Friction: {deck_model.statistics.get('average_activation_friction', 0)}",
                ha='center', fontsize=11, fontweight='bold', color='white')
        
        plt.savefig(f'{output_prefix}.png', dpi=300, bbox_inches='tight', facecolor='#1a1a1a')
        print(f"\nVisualization saved to: {output_prefix}.png")
        plt.close()


class DeckEncoder:
    """Main deck encoding orchestrator"""
    
    def __init__(self, cache: ScryfallCache):
        self.cache = cache
    
    def resolve_commander(self, partial_name: str, deck_card_names: List[str]) -> CardRecord:
        """Resolve partial commander name from cards in the deck"""
        partial_lower = partial_name.lower()
        matches = []
        
        for card_name in deck_card_names:
            if partial_lower in card_name.lower():
                card = self.cache.find_card(card_name)
                if card:
                    matches.append(card)
        
        if not matches:
            raise ValueError(f"No commander found matching '{partial_name}' in your deck")
        
        legendary_creatures = [
            c for c in matches 
            if 'legendary' in c.type_line.lower() and 'creature' in c.type_line.lower()
        ]
        
        if len(legendary_creatures) == 0:
            raise ValueError(f"No legendary creatures found for '{partial_name}' in your deck")
        
        if len(legendary_creatures) > 1:
            names = [c.name for c in legendary_creatures]
            raise ValueError(f"Ambiguous commander. Matches in deck: {', '.join(names)}")
        
        return legendary_creatures[0]
    
    def encode_card(self, card: CardRecord) -> EncodedCard:
        """Encode a single card with mechanical features"""
        features = MechanicsExtractor.extract_features(card)
        
        # Determine if this card can be played as a land from hand
        type_lower = card.type_line.lower()
        has_land_type = 'land' in type_lower
        
        # Determine if playable as land from hand based on layout
        is_playable_land = False
        
        if card.layout == 'modal_dfc':
            # Modal DFCs: You can choose to play either face
            # If either face is a land, you can play it as land
            is_playable_land = has_land_type
        elif card.layout == 'transform':
            # Transform DFCs: Must play FRONT face only
            # If front face is land -> playable as land
            # If front face is creature/artifact/etc -> NOT playable as land
            is_playable_land = (has_land_type and 
                               'creature' not in type_lower and 
                               'artifact' not in type_lower and
                               'enchantment' not in type_lower and
                               'planeswalker' not in type_lower)
        else:
            # Normal cards, Adventures, etc.
            is_playable_land = has_land_type
        
        return EncodedCard(
            name=card.name,
            cmc=card.cmc,
            type_line=card.type_line,
            color_identity=card.color_identity,
            oracle_text=card.oracle_text,
            mana_cost=card.mana_cost,
            is_land=is_playable_land,
            layout=card.layout,
            features=[asdict(f) for f in features]
        )
    
    def encode_deck(self, decklist_path: str, commander_partial: str) -> DeckModel:
        """Encode complete deck with validation"""
        card_tuples = DeckParser.parse_decklist(decklist_path)
        card_names = [name for name, _ in card_tuples]
        
        commander_card = self.resolve_commander(commander_partial, card_names)
        commander_identity = set(commander_card.color_identity)
        commander_encoded = self.encode_card(commander_card)
        
        encoded_cards = []
        illegal_cards = []
        
        for card_name, quantity in card_tuples:
            card = self.cache.find_card(card_name)
            if not card:
                print(f"Warning: Card not found: {card_name}")
                illegal_cards.append(f"{card_name} (NOT_FOUND)")
                continue
            
            if not EDHValidator.is_legal_in_identity(card, commander_identity):
                illegal_cards.append(f"{card.name} (COLOR_IDENTITY)")
                continue
            
            # Skip commander from the 99
            if card.name.lower() == commander_card.name.lower():
                continue
            
            # Add card multiple times based on quantity
            encoded = self.encode_card(card)
            for _ in range(quantity):
                encoded_cards.append(encoded)
        
        statistics = self._calculate_statistics(encoded_cards, commander_encoded)
        
        return DeckModel(
            commander=commander_encoded,
            cards=encoded_cards,
            illegal_cards=illegal_cards,
            statistics=statistics
        )
    
    def _calculate_statistics(self, cards: List[EncodedCard], commander: EncodedCard) -> Dict:
        """Calculate deck-level statistics"""
        feature_counts = {}
        total_friction = 0
        activated_count = 0
        x_spells = []
        
        for card in cards:
            for feature in card.features:
                feat_name = feature['feature']
                feature_counts[feat_name] = feature_counts.get(feat_name, 0) + 1
                
                if 'ACTIVATED' in feature.get('timing', []):
                    activated_count += 1
                    friction = len(feature.get('costs', []))
                    total_friction += friction
            
            # Track X-spells
            if 'X' in card.mana_cost:
                x_spells.append(card.name)
        
        avg_friction = total_friction / activated_count if activated_count > 0 else 0
        
        # Power level calculation
        power_score = self._calculate_power_level(cards, commander, feature_counts, x_spells)
        
        return {
            'total_cards': len(cards),
            'feature_counts': feature_counts,
            'activated_abilities': activated_count,
            'average_activation_friction': round(avg_friction, 2),
            'x_spells': x_spells,
            'x_spell_count': len(x_spells),
            'power_level': power_score
        }
    
    def _calculate_power_level(self, cards: List[EncodedCard], commander: EncodedCard, 
                               features: Dict[str, int], x_spells: List[str]) -> Dict:
        """Calculate deck power level metrics"""
        nonlands = [c for c in cards if not c.is_land]
        
        # Fast mana (0-2 CMC ramp/acceleration/mana rocks)
        fast_mana = len([c for c in nonlands if c.cmc <= 2 and 
                        any('RAMP' in f['feature'] or 'MANA_ROCK' in f['feature'] 
                            for f in c.features)])
        
        # Card advantage
        draw_sources = features.get('DRAW', 0)
        
        # Interaction
        removal = features.get('REMOVAL', 0)
        board_wipes = features.get('BOARD_WIPE', 0)
        counters = features.get('COUNTER', 0)
        
        # Efficiency (low CMC nonlands)
        low_cmc = len([c for c in nonlands if c.cmc <= 2])
        
        # X-spell potential (inflated late game power)
        x_spell_power = len(x_spells) * 1.5  # X-spells scale harder
        
        # Synergy density (cards with features / total nonlands)
        cards_with_features = len([c for c in nonlands if len(c.features) > 0])
        synergy_density = cards_with_features / len(nonlands) if nonlands else 0
        
        # Weighted power calculation
        power_components = {
            'fast_mana': fast_mana * 3,  # Fast mana is critical
            'card_advantage': draw_sources * 2,
            'interaction': (removal + board_wipes + counters) * 1.5,
            'efficiency': low_cmc * 0.5,
            'x_spell_scaling': x_spell_power,
            'synergy': synergy_density * 20
        }
        
        raw_score = sum(power_components.values())
        normalized_score = min(10, (raw_score / 15))  # Normalize to 1-10 scale
        
        return {
            'score': round(normalized_score, 2),
            'components': {k: round(v, 2) for k, v in power_components.items()},
            'raw_score': round(raw_score, 2),
            'fast_mana_count': fast_mana,
            'interaction_count': removal + board_wipes + counters,
            'removal_count': removal,
            'board_wipe_count': board_wipes,
            'efficiency_ratio': round(low_cmc / len(nonlands), 2) if nonlands else 0
        }

def main():
    """CLI entry point"""
    if len(sys.argv) < 3:
        print("Usage: python deck_encoder.py <decklist_file> <commander_partial_name> [--refresh] [--sim] [--sims N] [--turns T]")
        sys.exit(1)

    refresh_cache = '--refresh' in sys.argv
    run_sim = '--sim' in sys.argv
    sims = 10000
    turns = 12
    
    if '--sims' in sys.argv:
        idx = sys.argv.index('--sims')
        sims = int(sys.argv[idx + 1])
    
    if '--turns' in sys.argv:
        idx = sys.argv.index('--turns')
        turns = int(sys.argv[idx + 1])

    if refresh_cache:
        Path(CACHE_FILE).unlink(missing_ok=True)

    deck_filename = sys.argv[1]
    commander_partial = sys.argv[2]

    deck_path = DECKS_DIR / deck_filename
    if not deck_path.exists():
        print(f"Deck file not found: {deck_path}")
        sys.exit(1)

    OUTPUT_DIR.mkdir(exist_ok=True)

    cache = ScryfallCache()
    cache.load_or_fetch()
    encoder = DeckEncoder(cache)

    try:
        deck_model = encoder.encode_deck(str(deck_path), commander_partial)

        output_json = OUTPUT_DIR / f"{deck_path.stem}_encoded.json"
        with open(output_json, 'w', encoding='utf-8') as f:
            json.dump(asdict(deck_model), f, indent=2)

        print(f"\nDeck encoded: {deck_model.commander.name}")
        print(f"Total cards: {len(deck_model.cards) + 1}")
        print(f"Lands: {sum(1 for c in deck_model.cards if c.is_land)}")
        print(f"Nonlands: {sum(1 for c in deck_model.cards if not c.is_land)}")
        
        if deck_model.illegal_cards:
            print(f"Illegal cards: {len(deck_model.illegal_cards)}")

        print(f"Power Level: {deck_model.statistics.get('power_level', {}).get('score', 0)}/10")

        # Generate static analysis
        DeckAnalytics.create_visualizations(deck_model, output_prefix=str(OUTPUT_DIR / deck_path.stem))

        # Run simulation if requested
        if run_sim:
            from deck_simulator import DeckSimulator
            
            results = DeckSimulator.run_simulation(
                asdict(deck_model),
                sims=sims,
                turns=turns,
                output_dir=OUTPUT_DIR,
                deck_name=deck_path.stem
            )
            
            if results:
                print("Simulation complete.")
                
                # Generate comprehensive report
                report_path = OUTPUT_DIR / f"{deck_path.stem}_simulation_report.txt"
                DeckSimulator.generate_report(
                    results,
                    asdict(deck_model),
                    sims,
                    turns,
                    report_path
                )
                print(f"Report saved: {report_path}")
                
                # Generate visualization with embedded summary
                plot_path = OUTPUT_DIR / f"{deck_path.stem}_simulation.png"
                DeckSimulator.plot_simulation_results(results, asdict(deck_model), plot_path)
                print(f"Visualization saved: {plot_path}")
                
                # Quick summary
                classification = DeckSimulator.classify_deck_by_simulation(results)
                print(f"\nConsistency: {classification['consistency']} | Speed: {classification['speed']}")
                print(f"Screw: {results.screw_rate*100:.1f}% | Flood: {results.flood_rate*100:.1f}% | Normal: {results.ok_rate*100:.1f}%")

    except ValueError as e:
        print(f"Error: {e}")
        sys.exit(1)
    except FileNotFoundError as e:
        print(f"Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
