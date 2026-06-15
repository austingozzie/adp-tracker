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
        clean = re.sub(r"\s*\(.*?\)", "", name_text).strip()
        parts = clean.split()
        if len(parts) >= 2 and re.match(r"^[A-Z]{2,4}$", parts[-1]):
            team = parts[-1]
            name = " ".join(parts[:-1])
        else:
            team = ""
            name = clean
        key = name + "|" + pos
        players[key] = {"name": name, "team": team, "pos": pos, "adp_ud": ud_adp}

    print("  Found " + str(len(players)) + " Underdog players")
    return players


def fetch_sleeper_api():
    """Fetch Sleeper ADP directly from Sleeper's public API."""
    print("Fetching Sleeper ADP from Sleeper API...")

    # Get all NFL players (needed for name lookup)
    players_resp = requests.get("https://api.sleeper.app/v1/players/nfl", timeout=30)
    players_resp.raise_for_status()
    all_players = players_resp.json()
    print("  Loaded " + str(len(all_players)) + " players from Sleeper")

    # Build player_id -> name/pos map
    id_to_info = {}
    for pid, p in all_players.items():
        pos = p.get("position", "")
        if pos not in VALID_POS:
            continue
        full_name = p.get("full_name") or (
            (p.get("first_name", "") + " " + p.get("last_name", "")).strip()
        )
        if full_name:
            id_to_info[pid] = {"name": full_name, "pos": pos, "team": p.get("team", "")}

    # Get ADP data — Sleeper exposes draft pick averages via trending/stats
    # Use the projections/adp endpoint
    adp_resp = requests.get(
        "https://api.sleeper.app/v1/players/nfl/trending/add?lookback_hours=168&limit=500",
        timeout=15
    )
    
    # Sleeper doesn't have a direct ADP endpoint, so use the draft endpoint
    # Best approach: fetch from the NFL draft picks average endpoint
    # Actually use: GET https://api.sleeper.com/adp/nfl/2025/regular?position[]=...
    adp_url = "https://api.sleeper.com/adp/nfl/2025/regular?position[]=QB&position[]=RB&position[]=WR&position[]=TE&order_by=adp"
    try:
        adp_resp = requests.get(adp_url, headers=HEADERS, timeout=15)
        adp_resp.raise_for_status()
        adp_data = adp_resp.json()
        print("  ADP endpoint returned " + str(len(adp_data)) + " records")
    except Exception as e:
        print("  ADP endpoint failed: " + str(e))
        adp_data = []

    result = {}
    for entry in adp_data:
        pid = str(entry.get("player_id", ""))
        adp_val = entry.get("adp")
        if not pid or adp_val is None:
            continue
        info = id_to_info.get(pid)
        if not info:
            continue
        try:
            adp_float = float(adp_val)
        except (TypeError, ValueError):
            continue
        if adp_float <= 0:
            continue
        result[info["name"]] = {
            "adp_sleeper": adp_float,
            "adp_espn":    None,
            "adp_yahoo":   None,
        }

    print("  Found " + str(len(result)) + " players with Sleeper ADP")
    if result:
        sample = list(result.keys())[:8]
        print("  Sample: " + str(sample))
    return result


def normalize_name(name):
    """Normalize player name for fuzzy matching."""
    name = name.lower().strip()
    name = re.sub(r"[^a-z ]", "", name)  # removes periods, apostrophes, etc.
    name = re.sub(r"\s+", " ", name)
    return name


def merge_sources(ud_players, sleeper_data):
    """Merge Underdog with Sleeper ADP data, compute positional ranks."""

    def norm(name):
        name = re.sub(r"\b(jr|sr|ii|iii|iv)\.?\b", "", name.lower().strip())
        name = re.sub(r"[^a-z ]", "", name)  # removes periods so R.J. -> rj
        name = re.sub(r"\s+", " ", name).strip()
        return name

    # Normalized Sleeper lookup
    sleeper_norm = {norm(k): v for k, v in sleeper_data.items()}

    # First-initial + last name fallback (handles "R. Harvey" -> "RJ Harvey")
    sleeper_initial = {}
    for name in sleeper_data:
        parts = norm(name).split()
        if len(parts) >= 2:
            key = parts[0][0] + " " + parts[-1]
            sleeper_initial[key] = sleeper_data[name]

    merged = []
    unmatched = []
    for key, p in ud_players.items():
        name = p["name"]
        normed = norm(name)

        beat = sleeper_data.get(name) or sleeper_norm.get(normed)

        if not beat:
            parts = normed.split()
            if len(parts) >= 2:
                initial_key = parts[0][0] + " " + parts[-1]
                beat = sleeper_initial.get(initial_key)

        if not beat:
            unmatched.append(name)

        beat = beat or {}
        merged.append({
            "name":        name,
            "team":        p["team"],
            "pos":         p["pos"],
            "adp":         p["adp_ud"],
            "adp_ud":      p["adp_ud"],
            "adp_sleeper": beat.get("adp_sleeper"),
            "adp_espn":    beat.get("adp_espn"),
            "adp_yahoo":   beat.get("adp_yahoo"),
        })

    print("  Unmatched (" + str(len(unmatched)) + "): " + str(unmatched[:10]))

    from collections import defaultdict

    # Underdog positional ranks
    pos_ud = defaultdict(list)
    for p in merged:
        pos_ud[p["pos"]].append(p)
    for pos, group in pos_ud.items():
        group.sort(key=lambda x: x["adp_ud"])
        for i, p in enumerate(group):
            p["pos_rank_ud"] = pos + str(i + 1)

    # Sleeper positional ranks
    pos_sl = defaultdict(list)
    for p in merged:
        if p["adp_sleeper"] is not None:
            pos_sl[p["pos"]].append(p)
    for pos, group in pos_sl.items():
        group.sort(key=lambda x: x["adp_sleeper"])
        for i, p in enumerate(group):
            p["pos_rank_sleeper"] = pos + str(i + 1)
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
            "name":             p["name"],
            "team":             p["team"],
            "pos":              p["pos"],
            "adp":              p["adp_ud"],
            "adp_ud":           p["adp_ud"],
            "adp_sleeper":      p.get("adp_sleeper"),
            "adp_espn":         p.get("adp_espn"),
            "adp_yahoo":        p.get("adp_yahoo"),
            "pos_rank_ud":      p.get("pos_rank_ud"),
            "pos_rank_sleeper": p.get("pos_rank_sleeper"),
            "history":          hist,
        })
    return {
        "updated": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "source":  "FantasyPros (Underdog) + Sleeper API",
        "players": out,
    }


def main():
    out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "adp-data.json")
    ud_players  = fetch_fantasypros_bestball()
    sleeper_data = fetch_sleeper_api()
    players = merge_sources(ud_players, sleeper_data)
    existing = load_existing(out_path)
    output = build_output(players, existing)
    with open(out_path, "w") as f:
        json.dump(output, f, indent=2)
    print("\nSaved " + str(len(players)) + " players to adp-data.json")
    print("Updated: " + output["updated"])


if __name__ == "__main__":
    main()
