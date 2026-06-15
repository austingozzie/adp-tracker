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


def fetch_platform_adps():
    """Fetch Sleeper, ESPN, Yahoo ADP from FantasyPros PPR overall page."""
    print("Fetching platform ADPs from FantasyPros PPR overall...")
    url = "https://www.fantasypros.com/nfl/adp/ppr-overall.php"
    resp = requests.get(url, headers=HEADERS, timeout=15)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    table = soup.find("table")
    if not table:
        print("  WARNING: Could not find table")
        return {}

    thead = table.find("thead")
    headers = [th.get_text(strip=True) for th in thead.find_all("th")] if thead else []
    print("  PPR columns: " + str(headers))

    sl_idx    = next((i for i, h in enumerate(headers) if "sleeper" in h.lower()), None)
    espn_idx  = next((i for i, h in enumerate(headers) if "espn" in h.lower()), None)
    yahoo_idx = next((i for i, h in enumerate(headers) if "yahoo" in h.lower()), None)
    print("  Sleeper:" + str(sl_idx) + " ESPN:" + str(espn_idx) + " Yahoo:" + str(yahoo_idx))

    result = {}
    tbody = table.find("tbody")
    rows = tbody.find_all("tr") if tbody else []
    for row in rows:
        cells = row.find_all("td")
        name_text = cells[1].get_text(separator=" ", strip=True) if len(cells) > 1 else ""
        pos_text  = cells[2].get_text(strip=True) if len(cells) > 2 else ""
        pos = re.sub(r"\d+$", "", pos_text).strip()
        if pos not in VALID_POS:
            continue

        # Parse name — strip team suffix
        clean = re.sub(r"\s*\(.*?\)", "", name_text).strip()
        parts = clean.split()
        if len(parts) >= 2 and re.match(r"^[A-Z]{2,4}$", parts[-1]):
            name = " ".join(parts[:-1])
        else:
            name = clean

        def get_adp(idx):
            if idx is None or len(cells) <= idx:
                return None
            try:
                v = float(cells[idx].get_text(strip=True))
                return v if v > 0 else None
            except ValueError:
                return None

        sl_adp    = get_adp(sl_idx)
        espn_adp  = get_adp(espn_idx)
        yahoo_adp = get_adp(yahoo_idx)

        if sl_adp is None and espn_adp is None and yahoo_adp is None:
            continue

        result[name + "|" + pos] = {
            "adp_sleeper": sl_adp,
            "adp_espn":    espn_adp,
            "adp_yahoo":   yahoo_adp,
        }

    print("  Found " + str(len(result)) + " players with platform ADP")
    return result


def norm(name):
    name = re.sub(r"\b(jr|sr|ii|iii|iv)\.?\b", "", name.lower().strip())
    name = re.sub(r"[^a-z ]", "", name)  # removes periods so R.J. -> rj
    name = re.sub(r"\s+", " ", name).strip()
    return name


def merge_sources(ud_players, platform_data):
    """Merge Underdog with platform ADP data."""

    # Build normalized lookup by name|pos key
    plat_norm = {}
    for key, val in platform_data.items():
        parts = key.rsplit("|", 1)
        if len(parts) == 2:
            plat_norm[norm(parts[0]) + "|" + parts[1]] = val

    # First-initial + last name fallback per position
    plat_initial = {}
    for key, val in platform_data.items():
        parts = key.rsplit("|", 1)
        if len(parts) == 2:
            name_parts = norm(parts[0]).split()
            pos = parts[1]
            if len(name_parts) >= 2:
                init_key = name_parts[0][0] + " " + name_parts[-1] + "|" + pos
                plat_initial[init_key] = val

    merged = []
    unmatched = []
    for key, p in ud_players.items():
        name = p["name"]
        pos  = p["pos"]

        # Try exact key match first
        beat = platform_data.get(key)
        # Then normalized key
        if not beat:
            beat = plat_norm.get(norm(name) + "|" + pos)
        # Then initial fallback
        if not beat:
            n = norm(name).split()
            if len(n) >= 2:
                beat = plat_initial.get(n[0][0] + " " + n[-1] + "|" + pos)

        if not beat:
            unmatched.append(name)

        beat = beat or {}
        merged.append({
            "name":        name,
            "team":        p["team"],
            "pos":         pos,
            "adp":         p["adp_ud"],
            "adp_ud":      p["adp_ud"],
            "adp_sleeper": beat.get("adp_sleeper"),
            "adp_espn":    beat.get("adp_espn"),
            "adp_yahoo":   beat.get("adp_yahoo"),
        })

    print("  Unmatched (" + str(len(unmatched)) + "): " + str(unmatched[:10]))

    from collections import defaultdict

    pos_ud = defaultdict(list)
    for p in merged:
        pos_ud[p["pos"]].append(p)
    for pos, group in pos_ud.items():
        group.sort(key=lambda x: x["adp_ud"])
        for i, p in enumerate(group):
            p["pos_rank_ud"] = pos + str(i + 1)

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
        "source":  "FantasyPros (Underdog + Sleeper + ESPN + Yahoo)",
        "players": out,
    }


def main():
    out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "adp-data.json")
    ud_players    = fetch_fantasypros_bestball()
    platform_data = fetch_platform_adps()
    players  = merge_sources(ud_players, platform_data)
    existing = load_existing(out_path)
    output   = build_output(players, existing)
    with open(out_path, "w") as f:
        json.dump(output, f, indent=2)
    print("\nSaved " + str(len(players)) + " players to adp-data.json")
    print("Updated: " + output["updated"])


if __name__ == "__main__":
    main()
