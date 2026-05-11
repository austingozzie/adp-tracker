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
    """Fetch Sleeper ADP from BeatADP multi-platform table.
    Columns: Rank | Player+Team | BB10 | RTSports | Sleeper | DraftKings | Drafters | AVG
    """
    import re as _re
    print("Fetching Sleeper ADP from BeatADP...")
    url = "https://www.beatadp.com/platform-adp/sleeper"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
    except Exception as ex:
        print("  Failed: " + str(ex))
        return {}

    soup = BeautifulSoup(resp.text, "html.parser")
    table = soup.find("table")
    if not table:
        print("  WARNING: No table found")
        return {}

    thead = table.find("thead")
    header_cells = [th.get_text(strip=True) for th in thead.find_all("th")] if thead else []
    print("  Columns: " + str(header_cells))

    # Find Sleeper column index
    sl_idx = None
    for i, h in enumerate(header_cells):
        if "sleeper" in h.lower():
            sl_idx = i
            break
    if sl_idx is None:
        sl_idx = 4  # fallback
    print("  Sleeper col: " + str(sl_idx))

    # Find POS column
    pos_idx = None
    for i, h in enumerate(header_cells):
        if h.lower() in ["pos", "position"]:
            pos_idx = i
            break

    result = {}
    rows = table.find_all("tr")[1:]
    print("  Rows: " + str(len(rows)))
    if rows:
        print("  First row: " + str([c.get_text(strip=True) for c in rows[0].find_all("td")]))

    for row in rows:
        cells = row.find_all("td")
        if len(cells) <= sl_idx:
            continue

        # Sleeper ADP
        sl_text = cells[sl_idx].get_text(strip=True)
        try:
            sl_adp = float(sl_text)
        except ValueError:
            continue
        if sl_adp <= 0 or sl_adp > 300:
            continue

        # Player name+team in col 1: e.g. "Bijan RobinsonATL"
        name_team = cells[1].get_text(strip=True) if len(cells) > 1 else ""
        name_match = _re.match(r"^(.+?)([A-Z]{2,4})$", name_team)
        name = name_match.group(1).strip() if name_match else name_team.strip()
        if not name:
            continue

        # Position
        if pos_idx and len(cells) > pos_idx:
            pos_raw = cells[pos_idx].get_text(strip=True)
        else:
            # Try col 2 for pos+rank like "RB1"
            pos_raw = cells[2].get_text(strip=True) if len(cells) > 2 else ""
        pos = _re.sub(r"\d+$", "", pos_raw).strip()
        if pos not in VALID_POS:
            # Try extracting pos from name
            continue

        key = name + "|" + pos
        val = {"adp": sl_adp, "pos_rank": pos_raw.strip()}
        result[key] = val
        result[name] = val

    print("  Found " + str(len(result)//2) + " Sleeper players")
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
        if "|" not in key:
            norm = normalize_name(key)
            sleeper_norm[norm] = val
            continue
        name, pos = key.rsplit("|", 1)
        norm = normalize_name(name) + "|" + pos
        sleeper_norm[norm] = val
        sleeper_norm[normalize_name(name)] = val

    merged = []
    for key, p in ud_players.items():
        # Try exact match first
        sl_data = sleeper_data.get(key)
        if sl_data is None:
            norm_key = normalize_name(p["name"]) + "|" + p["pos"]
            sl_data = sleeper_norm.get(norm_key)
        if sl_data is None:
            sl_data = sleeper_norm.get(normalize_name(p["name"]))
        sleeper_adp = sl_data["adp"] if isinstance(sl_data, dict) else sl_data
        sleeper_pos_rank = sl_data["pos_rank"] if isinstance(sl_data, dict) else None
        merged.append({
            "name":                 p["name"],
            "team":                 p["team"],
            "pos":                  p["pos"],
            "adp":                  p["adp_ud"],
            "adp_ud":               p["adp_ud"],
            "adp_sleeper":          sleeper_adp,
            "pos_rank_sleeper_raw": sleeper_pos_rank,
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
            "adp_sleeper":      p.get("adp_sleeper"),
            "pos_rank_ud":      p.get("pos_rank_ud"),
            "pos_rank_sleeper": p.get("pos_rank_sleeper_raw") or p.get("pos_rank_sleeper"),
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
