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
        # FantasyPros format: "Bijan Robinson ATL (14)" or "Bijan Robinson ATL ()"
        # Strip bye week parentheses first
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
    """Fetch Sleeper + ESPN ADP from BeatADP platform comparison table."""
    import re as _re
    print("Fetching platform ADP from BeatADP...")
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
    header_cells = [th.get_text(strip=True).lower() for th in thead.find_all("th")] if thead else []
    print("  Columns: " + str(header_cells))

    sl_idx   = next((i for i,h in enumerate(header_cells) if "sleeper" in h), None)
    espn_idx = next((i for i,h in enumerate(header_cells) if "espn" in h), None)
    print("  Sleeper:" + str(sl_idx) + " ESPN:" + str(espn_idx))

    result = {}
    rows = table.find_all("tr")[1:]
    print("  Rows: " + str(len(rows)))

    for row in rows:
        cells = row.find_all("td")
        if len(cells) < 3:
            continue

        # Player name is in an <a> tag inside col 1
        name_cell = cells[1] if len(cells) > 1 else None
        if not name_cell:
            continue
        a_tag = name_cell.find("a")
        if a_tag:
            name = a_tag.get_text(strip=True)
        else:
            # fallback: strip team abbreviation from end
            raw = name_cell.get_text(strip=True)
            m = _re.match(r"^(.+?)([A-Z]{2,4})$", raw)
            name = m.group(1).strip() if m else raw.strip()

        if not name:
            continue

        def get_adp(idx):
            if idx is None or len(cells) <= idx:
                return None
            try:
                v = float(cells[idx].get_text(strip=True))
                return v if 0 < v <= 400 else None
            except ValueError:
                return None

        sl_adp   = get_adp(sl_idx)
        espn_adp = get_adp(espn_idx)

        if sl_adp is None and espn_adp is None:
            continue

        result[name] = {
            "adp_sleeper": sl_adp,
            "adp_espn":    espn_adp,
            "adp_yahoo":   None,
        }

    print("  Found " + str(len(result)) + " players from BeatADP")
    sample = list(result.keys())[:8]
    print("  Sample BeatADP names: " + str(sample))
    return result

def normalize_name(name):
    """Normalize player name for fuzzy matching."""
    import re
    name = name.lower().strip()
    name = re.sub(r"[^a-z ]", "", name)  # remove punctuation
    name = re.sub(r"\s+", " ", name)
    return name

def merge_sources(ud_players, beat_data):
    """Merge Underdog with BeatADP platform data, compute positional ranks."""
    import re as _re

    def norm(name):
        return _re.sub(r"[^a-z ]", "", name.lower().strip())

    # Build normalized BeatADP lookup
    beat_norm = {}
    for name, val in beat_data.items():
        beat_norm[norm(name)] = val

    merged = []
    unmatched = []
    for key, p in ud_players.items():
        name = p["name"]
        beat = beat_data.get(name) or beat_norm.get(norm(name)) or {}
        if not beat:
            unmatched.append(name)
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

    print("  Unmatched UD players (" + str(len(unmatched)) + "): " + str(unmatched[:10]))
    # Compute Underdog positional ranks
    from collections import defaultdict
    pos_ud = defaultdict(list)
    for p in merged:
        pos_ud[p["pos"]].append(p)
    for pos, group in pos_ud.items():
        group.sort(key=lambda x: x["adp_ud"])
        for i, p in enumerate(group):
            p["pos_rank_ud"] = pos + str(i + 1)

    # Compute Sleeper positional ranks
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
        "source":  "FantasyPros (Underdog + ESPN) + Sleeper API",
        "players": out,
    }


def main():
    out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "adp-data.json")
    ud_players  = fetch_fantasypros_bestball()
    # ESPN removed - not reliably available via scraping
    beat_data = fetch_sleeper()
    players = merge_sources(ud_players, beat_data)
    existing = load_existing(out_path)
    output = build_output(players, existing)
    with open(out_path, "w") as f:
        json.dump(output, f, indent=2)
    print("\nSaved " + str(len(players)) + " players to adp-data.json")
    print("Updated: " + output["updated"])


if __name__ == "__main__":
    main()
