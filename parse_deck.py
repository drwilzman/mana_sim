import requests
import json
import re
import argparse
from collections import defaultdict

SCRYFALL_API = "https://api.scryfall.com/cards/named"

def fetch_card_data(card_name):
    """Fetch card data from Scryfall API"""
    try:
        response = requests.get(SCRYFALL_API, params={"fuzzy": card_name})
        if response.status_code == 200:
            return response.json()
    except Exception as e:
        print(f"Error fetching {card_name}: {e}")
    return None

def parse_mana_cost(mana_cost, x_value):
    """Parse mana cost string like '{2}{B}{B}' into generic and pips"""
    if not mana_cost:
        return 0, []
    
    generic = 0
    pips = []
    has_x = False
    
    # Extract all mana symbols
    symbols = re.findall(r'\{([^}]+)\}', mana_cost)
    
    for symbol in symbols:
        if symbol.isdigit():
            generic += int(symbol)
        elif symbol == 'X':
            has_x = True
        elif '/' in symbol:  # Hybrid mana
            # Take first color for simplicity
            pips.append(symbol.split('/')[0])
        else:
            # Single color pip
            pips.append(symbol)
    
    if has_x:
        generic += x_value
    
    return generic, pips

def categorize_card(card_data, x_value, commander_name=None):
    """Categorize card into Commander, Land, Ramp, Fetch, or Spell"""
    type_line = card_data.get('type_line', '').lower()
    oracle_text = card_data.get('oracle_text', '').lower()
    card_name = card_data['name'].lower()
    
    # Check if this is the specified commander
    if commander_name and commander_name.lower() in card_name:
        generic, pips = parse_mana_cost(card_data.get('mana_cost', ''),x_value)
        return {'type': 'Commander', 'generic': generic, 'pips': pips, 'count': 1}
    
    # Basic lands
    if 'basic' in type_line and 'land' in type_line:
        name = card_data['name'].lower()
        if 'plains' in name:
            return {'type': 'Land', 'produces': ['W'], 'count': 1}
        elif 'island' in name:
            return {'type': 'Land', 'produces': ['U'], 'count': 1}
        elif 'swamp' in name:
            return {'type': 'Land', 'produces': ['B'], 'count': 1}
        elif 'mountain' in name:
            return {'type': 'Land', 'produces': ['R'], 'count': 1}
        elif 'forest' in name:
            return {'type': 'Land', 'produces': ['G'], 'count': 1}
    
    # Non-basic lands
    if 'land' in type_line:
        colors = card_data.get('produced_mana', [])
        if not colors:
            colors = ['C']
        return {'type': 'Land', 'produces': colors, 'count': 1}
    
    # Ramp artifacts
    if 'artifact' in type_line and any(word in oracle_text for word in ['add', 'mana', 'sol ring', 'signet']):
        generic, pips = parse_mana_cost(card_data.get('mana_cost', ''),x_value)
        # Guess produced mana from color identity
        colors = card_data.get('color_identity', ['C'])
        return {'type': 'Ramp', 'generic': generic, 'produces': colors, 'count': 1}
    
    # Everything else is a spell
    generic, pips = parse_mana_cost(card_data.get('mana_cost', ''),x_value)
    return {'type': 'Spell', 'generic': generic, 'pips': pips, 'count': 1}

def parse_decklist(text):
    """Parse decklist text into card entries"""
    cards = []
    lines = text.strip().split('\n')
    
    for line in lines:
        line = line.strip()
        if not line or line.startswith('Decklist') or line.startswith('Main') or line.startswith('Shared'):
            continue
        
        # Match "1 Card Name" or "Card Name"
        match = re.match(r'^(\d+)\s+(.+)$', line)
        if match:
            count = int(match.group(1))
            name = match.group(2).strip()
            # Remove double-faced card notation
            name = name.split('//')[0].strip()
            cards.append((count, name))
    
    return cards

def consolidate_cards(card_list):
    """Group cards by type and mana cost"""
    groups = defaultdict(lambda: {'count': 0, 'data': None})
    
    for card_entry in card_list:
        key = json.dumps(card_entry, sort_keys=True)
        if groups[key]['data'] is None:
            groups[key]['data'] = card_entry.copy()
            groups[key]['count'] = card_entry['count']
        else:
            groups[key]['count'] += card_entry['count']
    
    result = []
    for group in groups.values():
        data = group['data']
        data['count'] = group['count']
        result.append(data)
    
    return result

def main():
    parser = argparse.ArgumentParser(description='Convert MTG decklist to JSON')
    parser.add_argument('--input', type=str, required=True, help='Input text file with decklist')
    parser.add_argument('--output', type=str, required=True, help='Output JSON file')
    parser.add_argument('--name', type=str, default='deck', help='Deck name')
    parser.add_argument('--commander', type=str, required=True, help='Commander card name')
    parser.add_argument('--x_value', type=int, default=3, help='Mana Value of X')
    
    args = parser.parse_args()
    
    with open(args.input, 'r') as f:
        text = f.read()
    
    print("Parsing decklist...")
    cards = parse_decklist(text)
    
    print(f"Found {len(cards)} unique card entries. Fetching data from Scryfall...")
    
    card_data_list = []
    for count, name in cards:
        print(f"Fetching: {name}")
        card_data = fetch_card_data(name)
        if card_data:
            categorized = categorize_card(card_data, args.x_value, args.commander)
            categorized['count'] = count
            card_data_list.append(categorized)
    
    print("Consolidating similar cards...")
    consolidated = consolidate_cards(card_data_list)
    
    # Sort: Commander first, then Lands, then Ramp, then Spells by cost
    def sort_key(card):
        type_order = {'Commander': 0, 'Land': 1, 'Ramp': 2, 'Fetch': 3, 'Spell': 4}
        return (type_order.get(card['type'], 5), card.get('generic', 0), len(card.get('pips', [])))
    
    consolidated.sort(key=sort_key)
    
    deck = {
        'name': args.name,
        'cards': consolidated
    }
    
    with open(args.output, 'w') as f:
        json.dump(deck, f, indent=2)
    
    print(f"Deck saved to {args.output}")
    print(f"Total cards: {sum(c['count'] for c in consolidated)}")

if __name__ == '__main__':
    main()
