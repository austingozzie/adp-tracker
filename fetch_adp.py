import json, re, sys, os
from datetime import datetime

try:
    import requests
    from bs4 import BeautifulSoup
except ImportError:
    os.system(sys.executable + " -m pip install requests beautifulsoup4 -q")
    import requests
    from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}
VALID_POS = {"QB", "RB", "WR", "TE"}


def fetch_fantasypros_bestball():
    """Fetch Underdog ADP from FantasyPros best ball page."""
    print("Fetching Underdog ADP from FantasyPros best ball...")
    url = "https://www.fantasypros.com/nfl/adp/best-ball-overall.php"
    resp = requests.get(url, headers=HEADERS, timeout=15)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    table = soup.find("table")
    if not table:
        raise ValueError("Could not find best ball ADP table")

    thead = table.find("thead")
    headers = [th.get_text(strip=True) for th in thead.find_all("th")] if thead else []
    print("  Best ball columns: " + str(headers))

    ud_idx = next((i for i, h in enumerate(headers) if "underdog" in h.lower()), 5)
    print("  Underdog col: " + str(ud_idx))

    players = {}
    tbody = table.find("tbody")
    rows = tbody.find_all("tr") if tbody else []
    for row in rows:
        cells = row.find_all("td")
        if len(cells) <= ud_idx:
            continue
        name_text = cells[1].get_text(separator=" ", strip=True) if len(cells) > 1 else ""
        pos_text  = cells[2].get_text(strip=True) if len(cells) > 2 else ""
        pos = re.sub(r"\d+$", "", pos_text).strip()
        if pos not in VALID_POS:
            continue
        ud_text = cells[ud_idx].get_text(strip=True)
        try:
            ud_adp = float(ud_text)
        except ValueError:
            continue
        if ud_adp <= 0:
            continue
        parts = name_text.split()
        if len(parts) >= 2 and re.match(r"^[A-Z]{2,4}$", parts[-1]):
            team = parts[-1]
            name = " ".join(parts[:-1])
        else:
            team = ""
            name = name_text
        key = name + "|" + pos
        players[key] = {"name": name, "team": team, "pos": pos, "adp_ud": ud_adp}

    print("  Found " + str(len(players)) + " Underdog players")
    return players


def fetch_fantasypros_espn():
    """Fetch ESPN ADP from FantasyPros standard overall ADP page."""
    print("Fetching ESPN ADP from FantasyPros overall...")
    url = "https://www.fantasypros.com/nfl/adp/ppr-overall.php"
    resp = requests.get(url, headers=HEADERS, timeout=15)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    table = soup.find("table")
    if not table:
        print("  WARNING: Could not find ESPN ADP table")
        return {}

    thead = table.find("thead")
    headers = [th.get_text(strip=True) for th in thead.find_all("th")] if thead else []
    print("  Overall columns: " + str(headers))

    espn_idx = next((i for i, h in enumerate(headers) if "espn" in h.lower()), None)
    if espn_idx is None:
        print("  WARNING: ESPN column not found")
        return {}
    print("  ESPN col: " + str(espn_idx))

    result = {}
    tbody = table.find("tbody")
    rows = tbody.find_all("tr") if tbody else []
    for row in rows:
        cells = row.find_all("td")
        if len(cells) <= espn_idx:
            continue
        name_text = cells[1].get_text(separator=" ", strip=True) if len(cells) > 1 else ""
        pos_text  = cells[2].get_text(strip=True) if len(cells) > 2 else ""
        pos = re.sub(r"\d+$", "", pos_text).strip()
        if pos not in VALID_POS:
            continue
        espn_text = cells[espn_idx].get_text(strip=True)
        try:
            espn_adp = float(espn_text)
        except ValueError:
            continue
        if espn_adp <= 0:
            continue
        parts = name_text.split()
        name = " ".join(parts[:-1]) if len(parts) >= 2 and re.match(r"^[A-Z]{2,4}$", parts[-1]) else name_text
        key = name + "|" + pos
        result[key] = espn_adp

    print("  Found " + str(len(result)) + " ESPN ADP values")
    return result


def fetch_sleeper():
    """Fetch real Sleeper draft ADP from BeatADP.com."""
    print("Fetching Sleeper ADP from BeatADP...")
    # Try best ball format first, fall back to half PPR
    urls = [
        "https://www.beatadp.com/platform-adp/sleeper?draftType=BEST_BALL&scoringFormat=PPR",
        "https://www.beatadp.com/platform-adp/sleeper?draftType=REDRAFT&scoringFormat=PPR",
        "https://www.beatadp.com/platform-adp/sleeper",
    ]
    soup = None
    for url in urls:
        try:
            resp = requests.get(url, headers=HEADERS, timeout=15)
            resp.raise_for_status()
            s = BeautifulSoup(resp.text, "html.parser")
            table = s.find("table")
            if table:
                soup = s
                print("  Got table from: " + url)
                break
        except Exception as ex:
            print("  Failed: " + str(ex))
            continue

    if not soup:
        print("  WARNING: Could not fetch Sleeper ADP from BeatADP")
        return {}

    table = soup.find("table")
    result = {}
    rows = table.find_all("tr")[1:] if table else []
    for row in rows:
        cells = row.find_all("td")
        if len(cells) < 4:
            continue
        try:
            rank = float(cells[0].get_text(strip=True))
        except ValueError:
            continue
        name_cell = cells[2].get_text(strip=True) if len(cells) > 2 else ""
        pos_cell  = cells[3].get_text(strip=True) if len(cells) > 3 else ""
        # pos_cell looks like "RB 1" or "WR 5"
        pos = pos_cell.split()[0] if pos_cell else ""
        if pos not in VALID_POS:
            continue
        if not name_cell or rank > 300:
            continue
        # Store by name|pos key
        key = name_cell + "|" + pos
        result[key] = rank
        # Also store name-only as fallback
        result[name_cell] = rank

    print("  Found " + str(len(result)) + " Sleeper ADP values")
    return result


def normalize_name(name):
    """Normalize player name for fuzzy matching."""
    import re
    name = name.lower().strip()
    name = re.sub(r"[^a-z ]", "", name)  # remove punctuation
    name = re.sub(r"\s+", " ", name)
    return name

def merge_sources(ud_players, sleeper_data):
    """Merge Underdog and Sleeper, compute positional ranks."""
    # Build normalized sleeper lookup
    sleeper_norm = {}
    for key, val in sleeper_data.items():
        name, pos = key.rsplit("|", 1)
        norm = normalize_name(name) + "|" + pos
        sleeper_norm[norm] = val
        # Also store name-only for fallback
        sleeper_norm[normalize_name(name)] = val

    merged = []
    for key, p in ud_players.items():
        # Try exact match first
        sleeper_adp = sleeper_data.get(key)
        if sleeper_adp is None:
            # Try normalized match
            norm_key = normalize_name(p["name"]) + "|" + p["pos"]
            sleeper_adp = sleeper_norm.get(norm_key)
        if sleeper_adp is None:
            # Try name-only normalized match
            sleeper_adp = sleeper_norm.get(normalize_name(p["name"]))
        merged.append({
            "name":        p["name"],
            "team":        p["team"],
            "pos":         p["pos"],
            "adp":         p["adp_ud"],
            "adp_ud":      p["adp_ud"],
            "adp_sleeper": sleeper_adp,
        })

    # Compute Underdog positional ranks (sort by adp_ud within each pos)
    from collections import defaultdict
    pos_groups_ud = defaultdict(list)
    for p in merged:
        pos_groups_ud[p["pos"]].append(p)
    for pos, group in pos_groups_ud.items():
        group.sort(key=lambda x: x["adp_ud"])
        for i, p in enumerate(group):
            p["pos_rank_ud"] = pos + str(i + 1)

    # Compute Sleeper positional ranks (sort by adp_sleeper within each pos)
    pos_groups_sl = defaultdict(list)
    for p in merged:
        if p["adp_sleeper"] is not None:
            pos_groups_sl[p["pos"]].append(p)
    for pos, group in pos_groups_sl.items():
        group.sort(key=lambda x: x["adp_sleeper"])
        for i, p in enumerate(group):
            p["pos_rank_sleeper"] = pos + str(i + 1)

    # Set missing Sleeper pos rank to None
    for p in merged:
        if "pos_rank_sleeper" not in p:
            p["pos_rank_sleeper"] = None

    return merged


def load_existing(path):
    if not os.path.exists(path):
        return {}
    with open(path) as f:
        data = json.load(f)
    existing = {}
    for p in data.get("players", []):
        key = p["name"] + "|" + p["pos"]
        existing[key] = p
    return existing


def build_output(players, existing):
    today = datetime.now().strftime("%b %-d")
    out = []
    for p in players:
        key  = p["name"] + "|" + p["pos"]
        prev = existing.get(key, {})
        hist = prev.get("history", [])
        if not hist or hist[-1]["date"] != today:
            hist.append({"date": today, "adp": p["adp_ud"]})
        hist = hist[-30:]
        out.append({
            "name":           p["name"],
            "team":           p["team"],
            "pos":            p["pos"],
            "adp":            p["adp_ud"],
            "adp_ud":         p["adp_ud"],
            "adp_sleeper":    p.get("adp_sleeper"),
            "pos_rank_ud":    p.get("pos_rank_ud"),
            "pos_rank_sleeper": p.get("pos_rank_sleeper"),
            "history":        hist,
        })
    return {
        "updated": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "source":  "FantasyPros (Underdog + ESPN) + Sleeper API",
        "players": out,
    }


def main():
    out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "adp-data.json")
    ud_players  = fetch_fantasypros_bestball()
    # ESPN removed - not reliably available via scraping
    sleeper_data = fetch_sleeper()
    players = merge_sources(ud_players, sleeper_data)
    existing = load_existing(out_path)
    output = build_output(players, existing)
    with open(out_path, "w") as f:
        json.dump(output, f, indent=2)
    print("\nSaved " + str(len(players)) + " players to adp-data.json")
    print("Updated: " + output["updated"])


if __name__ == "__main__":
    main()
