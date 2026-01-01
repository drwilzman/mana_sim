
"""
MTG Commander deck analyzer:
text -> JSON -> Rust sim -> plots -> optional swap tests
"""

import subprocess
import json
import argparse
import matplotlib.pyplot as plt
from pathlib import Path
from datetime import datetime
import requests
import re
from collections import defaultdict
import hashlib
import shutil
import itertools
from collections import Counter
import copy

SCRY = "https://api.scryfall.com/cards/named"
CACHE = Path(".card_cache")
CACHE.mkdir(exist_ok=True)

import tempfile

def run_sim_in_memory(deck_dict, sims, turns):
    """Run Rust sim using a temporary file in RAM, deleted after use."""
    with tempfile.NamedTemporaryFile("w+", suffix=".json", delete=False) as tmp:
        json.dump(deck_dict, tmp)
        tmp_path = Path(tmp.name)

    # Run the simulation pointing at the temp file
    cmd = [
        "cargo", "run", "--release", "--",
        "--deck", str(tmp_path),
        "--sims", str(sims),
        "--turns", str(turns),
        "--output", "tmp_out.json"
    ]
    r = subprocess.run(cmd, capture_output=True, text=True)
    tmp_path.unlink()  # delete temp deck file immediately

    if r.returncode != 0:
        print("Simulation error:", r.stderr)
        return None

    result = json.load(open("tmp_out.json"))
    Path("tmp_out.json").unlink()  # delete output file
    return result



# ---------- Scryfall ----------

def cache_key(name):
    return CACHE / f"{hashlib.md5(name.lower().encode()).hexdigest()}.json"


def fetch_card(name):
    f = cache_key(name)
    if f.exists():
        try:
            return json.load(open(f))
        except:
            pass

    r = requests.get(SCRY, params={"fuzzy": name})
    if r.status_code == 200:
        data = r.json()
        json.dump(data, open(f, "w"))
        return data
    return None


# ---------- Parsing ----------

def parse_mana(cost, x):
    if not cost:
        return 0, []

    g = 0
    p = []
    has_x = False

    for s in re.findall(r"\{([^}]+)\}", cost):
        if s.isdigit():
            g += int(s)
        elif s == "X":
            has_x = True
        elif "/" in s:
            p.append(s.split("/")[0])
        else:
            p.append(s)

    if has_x:
        g += x

    return g, p


def categorize(card, x, commander):
    t = card.get("type_line", "").lower()
    o = card.get("oracle_text", "").lower()
    name = card["name"].lower()

    if commander and commander.lower() in name:
        g, p = parse_mana(card.get("mana_cost", ""), x)
        return {"type": "Commander", "generic": g, "pips": p}

    if "basic land" in t:
        m = {
            "plains": "W", "island": "U", "swamp": "B",
            "mountain": "R", "forest": "G"
        }
        for k, v in m.items():
            if k in name:
                return {"type": "Land", "produces": [v]}

    if "land" in t:
        cols = card.get("produced_mana") or card.get("color_identity") or ["C"]
        return {"type": "Land", "produces": cols}

    if "artifact" in t and "add" in o and "mana" in o:
        g, p = parse_mana(card.get("mana_cost", ""), x)
        cols = card.get("produced_mana") or card.get("color_identity") or ["C"]
        return {"type": "Ramp", "generic": g, "produces": cols, "pips": p}

    g, p = parse_mana(card.get("mana_cost", ""), x)
    return {"type": "Spell", "generic": g, "pips": p}


def parse_deck(text):
    sec = "main"
    out = {"main": [], "maybe": [], "sideboard": []}

    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue

        l = line.lower()
        if l.startswith(("main", "deck")):
            sec = "main"; continue
        if l.startswith(("maybe", "consider")):
            sec = "maybe"; continue
        if l.startswith(("side", "board")):
            sec = "sideboard"; continue

        m = re.match(r"^(\d+)\s+(.+)$", line)
        if m:
            n = int(m.group(1))
            name = m.group(2).split("//")[0].strip()
            out[sec].append((n, name))

    return out


def consolidate(cards):
    g = defaultdict(int)
    meta = {}

    for c in cards:
        key = (
            c["name"], c["type"],
            c.get("generic", 0),
            tuple(c.get("pips", []))
        )
        g[key] += c["count"]
        meta[key] = c

    out = []
    for k, cnt in g.items():
        d = meta[k].copy()
        d["count"] = cnt
        out.append(d)
    return out


# ---------- JSON ----------

def text_to_json(path, commander, x, include_maybe):
    parsed = parse_deck(open(path).read())
    main = parsed["main"]
    maybe = parsed["maybe"]

    cards = []
    for n, name in main:
        c = fetch_card(name)
        if not c: continue
        d = categorize(c, x, commander)
        d["count"] = n
        d["name"] = c["name"]
        cards.append(d)

    cards = consolidate(cards)

    may = []
    for n, name in maybe:
        c = fetch_card(name)
        if not c: continue
        d = categorize(c, x, commander)
        d["count"] = n
        d["name"] = c["name"]
        may.append(d)

    deck = {"name": Path(path).stem, "cards": cards, "maybe": may}
    out = f"{deck['name']}.json"
    json.dump(deck, open(out, "w"), indent=2)
    return out


# ---------- Swap testing ----------

def sim_score(a, b):
    s = 0
    if a["type"] != b["type"]: s += 10
    s += abs((a.get("generic", 0) + len(a.get("pips", []))) -
             (b.get("generic", 0) + len(b.get("pips", [])))) * 2
    s += len(set(a.get("pips", [])) ^ set(b.get("pips", [])))
    return s


def gen_swaps(deck):
    if not deck["maybe"]:
        return []

    tests = []
    for m in deck["maybe"]:
        cands = []
        for i, c in enumerate(deck["cards"]):
            if c["type"] in ("Commander", "Land"):
                continue
            cands.append((sim_score(m, c), i))

        for _, idx in sorted(cands)[:3]:
            tests.append((idx, m))
    return tests


# ---------- Simulation ----------

def run_sim(deck, sims, turns):
    cmd = [
        "cargo", "run", "--release", "--",
        "--deck", deck, "--sims", str(sims),
        "--turns", str(turns), "--output", "tmp.json"
    ]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print(r.stderr)
        return None

    data = json.load(open("tmp.json"))
    Path("tmp.json").unlink()
    return data

def gen_land_variants(deck, min_lands=35, max_lands=41, step=1):
    COLOR_LAND_NAMES = {
        "W": "Plains", "U": "Island", "B": "Swamp",
        "R": "Mountain", "G": "Forest", "C": "Wastes"
    }

    commander_card = next((c for c in deck["cards"] if c["type"] == "Commander"), None)
    colors = list(set(commander_card.get("pips", []))) if commander_card else []

    # Keep existing ramp artifacts
    existing_ramp = [c for c in deck["cards"] if c["type"] == "Ramp"]
    existing_lands = [c for c in deck["cards"] if c["type"] == "Land"]
    non_lands = [c for c in deck["cards"] if c["type"] not in ("Land", "Ramp", "Commander")]

    variants = []
    seen = set()

    for land_count in range(min_lands, max_lands + 1, step):
        if colors:
            base = land_count // len(colors)
            remainder = land_count % len(colors)
            color_distribution = [base + (1 if i < remainder else 0) for i in range(len(colors))]
        else:
            color_distribution = [land_count]

        # Create unique key for this configuration
        config_key = (land_count, tuple(color_distribution))
        if config_key in seen:
            continue
        seen.add(config_key)

        new_deck = {
            "name": f"lands_{land_count}_{'_'.join(map(str, color_distribution))}",
            "cards": [],
            "maybe": deck.get("maybe", [])
        }

        # Add commander
        if commander_card:
            new_deck["cards"].append(copy.deepcopy(commander_card))

        # Add all non-land cards
        for c in non_lands:
            new_deck["cards"].append(copy.deepcopy(c))

        # Add ramp artifacts (preserve existing)
        for r in existing_ramp:
            new_deck["cards"].append(copy.deepcopy(r))

        # Add lands by color
        for i, n in enumerate(color_distribution):
            color = colors[i] if i < len(colors) else "C"
            # Find best matching land from existing lands
            land = next((l for l in existing_lands if color in l.get("produces", [])), None)
            
            if land:
                land_copy = copy.deepcopy(land)
                land_copy["count"] = n
                new_deck["cards"].append(land_copy)
            else:
                # Create basic land
                new_deck["cards"].append({
                    "type": "Land",
                    "produces": [color],
                    "count": n,
                    "name": COLOR_LAND_NAMES.get(color, "Wastes"),
                    "pips": []
                })

        # Adjust total to 99 cards
        total_cards = sum(c["count"] for c in new_deck["cards"] if c["type"] != "Commander")
        diff = 99 - total_cards
        
        if diff > 0:
            # Add colorless lands to reach 99
            new_deck["cards"].append({
                "type": "Land",
                "produces": ["C"],
                "count": diff,
                "name": "Wastes",
                "pips": []
            })
        elif diff < 0:
            # Remove lands from end
            for c in reversed(new_deck["cards"]):
                if c["type"] == "Land":
                    reduction = min(c["count"], abs(diff))
                    c["count"] -= reduction
                    diff += reduction
                    if diff == 0:
                        break
            new_deck["cards"] = [c for c in new_deck["cards"] if c["count"] > 0]

        variants.append(new_deck)

    return variants


def run_land_sim(deck, sims, turns):
    """
    Run simulation for all land variants and score them.
    Returns list of tuples: (score, deck_dict, sim_result)
    """
    variants = gen_land_variants(deck)
    results = []
    
    for var in variants:
        sim_result = run_sim_in_memory(var, sims, turns)
        if not sim_result:
            continue
        
        # Weight early turns more heavily
        weighted_ok = sum((ok * (1.0 + 0.1 * min(i, 5))) for i, ok in enumerate(sim_result["ok"]))
        weighted_screw = sum((screw * (1.5 + 0.2 * min(i, 5))) for i, screw in enumerate(sim_result["screw"]))
        weighted_flood = sum((flood * 0.8) for flood in sim_result["flood"])
        
        score = weighted_ok - weighted_screw - weighted_flood
        results.append((score, var, sim_result))

    results.sort(reverse=True, key=lambda x: x[0])
    return results

# ---------- Plot ----------

def plot(stats, name, out):
    out = Path(out); out.mkdir(exist_ok=True)
    t = range(1, len(stats["ok"]) + 1)

    ok = stats["ok"]
    screw = stats["screw"]
    flood = stats["flood"]

    cum_ok = [sum(ok[:i+1]) / (i+1) for i in range(len(ok))]

    plt.figure(figsize=(13, 8))

    plt.plot(t, ok, lw=2.5, label="OK")
    plt.plot(t, screw, lw=1.8, alpha=0.8, label="Screw")
    plt.plot(t, flood, lw=1.8, alpha=0.8, label="Flood")

    plt.plot(t, cum_ok, lw=3, ls="--", label="Cumulative OK")

    peak = max(range(len(ok)), key=lambda i: ok[i])
    plt.axvline(peak + 1, ls=":", alpha=0.6)
    plt.text(
        peak + 1, ok[peak],
        f"Peak OK: T{peak+1}",
        ha="left", va="bottom"
    )

    plt.xlabel("Turn")
    plt.ylabel("Probability")
    plt.title(f"{name.upper()} — Mana Stability")
    plt.legend()
    plt.grid(alpha=0.25)

    p = out / f"{name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
    plt.savefig(p, dpi=220)
    plt.close()
    print("Saved:", p)



# ---------- CLI ----------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("deck")
    ap.add_argument("--commander", required=True)
    ap.add_argument("--sims", type=int, default=50000)
    ap.add_argument("--turns", type=int, default=20)
    ap.add_argument("--x", type=int, default=3)
    ap.add_argument("--out", default="output")
    ap.add_argument("--clear-cache", action="store_true")
    ap.add_argument("--test-swaps", action="store_true")
    ap.add_argument("--test-lands", action="store_true", help="Optimize land counts and colors")

    args = ap.parse_args()

    if args.clear_cache:
        shutil.rmtree(CACHE); CACHE.mkdir()

    deck_json = text_to_json(args.deck, args.commander, args.x, False)
    base = run_sim(deck_json, args.sims, args.turns)
    if not base: return

    plot(base, Path(deck_json).stem, args.out)

    if args.test_lands:
        deck = json.load(open(deck_json))
        land_results = run_land_sim(deck, args.sims, args.turns)
        print("\nTop land configurations:")
        for score, variant, res in land_results[:10]:
            land_counts = [(c["produces"], c["count"]) for c in variant["cards"] if c["type"] in ("Land", "Ramp")]
            print(f"Score: {score:.2f} — Land counts: {land_counts}")

    if args.test_swaps:
        deck = json.load(open(deck_json))
        base_score = sum(base["ok"]) - sum(base["screw"]) - sum(base["flood"])
        swaps = gen_swaps(deck)
        recommendations = []

        for idx, maybe_card in swaps:
            test_deck = deck.copy()
            test_deck["cards"] = deck["cards"].copy()
            test_deck["cards"][idx] = maybe_card

            result = run_sim_in_memory(test_deck, args.sims, args.turns)
            if result:
                score = sum(result["ok"]) - sum(result["screw"]) - sum(result["flood"])
                score_improvement = score - base_score
                if score_improvement > 0:
                    old_card_name = deck["cards"][idx]["name"]
                    new_card_name = maybe_card["name"]
                    recommendations.append((score_improvement, old_card_name, new_card_name))

        # Sort and show top improvements
        recommendations.sort(reverse=True)
        if recommendations:
            print("\nTop swap recommendations:")
            for score, old, new in recommendations[:10]:
                print(f"Replace '{old}' with '{new}' → score improvement: {score:.2f}")
        else:
            print("\nNo positive swap improvements found.")

    Path(deck_json).unlink()


if __name__ == "__main__":
    main()

