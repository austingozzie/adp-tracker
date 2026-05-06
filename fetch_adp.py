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
    url = "https://www.fantasypros.com/nfl/adp/overall.php"
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
    """Fetch Sleeper ADP from Sleeper's public API."""
    print("Fetching Sleeper ADP...")
    # Sleeper trending/ADP endpoint
    url = "https://api.sleeper.app/v1/players/nfl"
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    data = resp.json()

    result = {}
    for pid, p in data.items():
        pos = p.get("fantasy_positions", [None])[0] if p.get("fantasy_positions") else None
        if pos not in VALID_POS:
            continue
        rank = p.get("search_rank")
        if not rank or rank == 9999999:
            continue
        first = p.get("first_name", "")
        last  = p.get("last_name", "")
        name  = (first + " " + last).strip()
        if not name:
            continue
        key = name + "|" + pos
        result[key] = float(rank)

    print("  Found " + str(len(result)) + " Sleeper ADP values")
    return result


def merge_sources(ud_players, espn_data, sleeper_data):
    """Merge all three sources, keyed on Underdog players."""
    merged = []
    for key, p in ud_players.items():
        espn_adp    = espn_data.get(key)
        sleeper_adp = sleeper_data.get(key)
        merged.append({
            "name":       p["name"],
            "team":       p["team"],
            "pos":        p["pos"],
            "adp":        p["adp_ud"],
            "adp_ud":     p["adp_ud"],
            "adp_espn":   espn_adp,
            "adp_sleeper": sleeper_adp,
        })
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
            "name":        p["name"],
            "team":        p["team"],
            "pos":         p["pos"],
            "adp":         p["adp_ud"],
            "adp_ud":      p["adp_ud"],
            "adp_espn":    p.get("adp_espn"),
            "adp_sleeper": p.get("adp_sleeper"),
            "history":     hist,
        })
    return {
        "updated": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "source":  "FantasyPros (Underdog + ESPN) + Sleeper API",
        "players": out,
    }


def main():
    out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "adp-data.json")
    ud_players  = fetch_fantasypros_bestball()
    espn_data   = fetch_fantasypros_espn()
    sleeper_data = fetch_sleeper()
    players = merge_sources(ud_players, espn_data, sleeper_data)
    existing = load_existing(out_path)
    output = build_output(players, existing)
    with open(out_path, "w") as f:
        json.dump(output, f, indent=2)
    print("\nSaved " + str(len(players)) + " players to adp-data.json")
    print("Updated: " + output["updated"])


if __name__ == "__main__":
    main()
