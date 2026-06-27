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


def fetch_consensus_adp():
    """Fetch consensus AVG ADP from FantasyPros PPR overall page."""
    print("Fetching consensus ADP from FantasyPros PPR overall...")
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

    # Try AVG first, fall back to last numeric column
    avg_idx = next((i for i, h in enumerate(headers) if "avg" in h.lower()), None)
    if avg_idx is None and headers:
        avg_idx = len(headers) - 1
        print("  No AVG column found, using last column: " + headers[avg_idx])
    print("  AVG col: " + str(avg_idx))

    result = {}
    tbody = table.find("tbody")
    rows = tbody.find_all("tr") if tbody else []
    for row in rows:
        cells = row.find_all("td")
        if avg_idx is None or len(cells) <= avg_idx:
            continue
        name_text = cells[1].get_text(separator=" ", strip=True) if len(cells) > 1 else ""
        pos_text  = cells[2].get_text(strip=True) if len(cells) > 2 else ""
        pos = re.sub(r"\d+$", "", pos_text).strip()
        if pos not in VALID_POS:
            continue
        avg_text = cells[avg_idx].get_text(strip=True)
        try:
            avg_adp = float(avg_text)
        except ValueError:
            continue
        if avg_adp <= 0:
            continue
        clean = re.sub(r"\s*\(.*?\)", "", name_text).strip()
        parts = clean.split()
        name = " ".join(parts[:-1]) if len(parts) >= 2 and re.match(r"^[A-Z]{2,4}$", parts[-1]) else clean
        result[name + "|" + pos] = avg_adp

    print("  Found " + str(len(result)) + " consensus ADP values")
    return result


def norm(name):
    name = re.sub(r"\b(jr|sr|ii|iii|iv)\.?\b", "", name.lower().strip())
    name = re.sub(r"[^a-z ]", "", name)
    name = re.sub(r"\s+", " ", name).strip()
    return name


def merge_sources(ud_players, consensus_data):
    """Merge Underdog with consensus ADP data."""

    cons_norm = {}
    for key, val in consensus_data.items():
        parts = key.rsplit("|", 1)
        if len(parts) == 2:
            cons_norm[norm(parts[0]) + "|" + parts[1]] = val

    cons_initial = {}
    for key, val in consensus_data.items():
        parts = key.rsplit("|", 1)
        if len(parts) == 2:
            name_parts = norm(parts[0]).split()
            pos = parts[1]
            if len(name_parts) >= 2:
                cons_initial[name_parts[0][0] + " " + name_parts[-1] + "|" + pos] = val

    merged = []
    unmatched = []
    for key, p in ud_players.items():
        name = p["name"]
        pos  = p["pos"]

        adp_cons = consensus_data.get(key)
        if not adp_cons:
            adp_cons = cons_norm.get(norm(name) + "|" + pos)
        if not adp_cons:
            n = norm(name).split()
            if len(n) >= 2:
                adp_cons = cons_initial.get(n[0][0] + " " + n[-1] + "|" + pos)

        if not adp_cons:
            unmatched.append(name)

        merged.append({
            "name":        name,
            "team":        p["team"],
            "pos":         pos,
            "adp":         p["adp_ud"],
            "adp_ud":      p["adp_ud"],
            "adp_consensus": adp_cons,
            "adp_sleeper": None,
            "adp_espn":    None,
            "adp_yahoo":   None,
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

    pos_cons = defaultdict(list)
    for p in merged:
        if p["adp_consensus"] is not None:
            pos_cons[p["pos"]].append(p)
    for pos, group in pos_cons.items():
        group.sort(key=lambda x: x["adp_consensus"])
        for i, p in enumerate(group):
            p["pos_rank_consensus"] = pos + str(i + 1)
    for p in merged:
        if "pos_rank_consensus" not in p:
            p["pos_rank_consensus"] = None
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
            "name":               p["name"],
            "team":               p["team"],
            "pos":                p["pos"],
            "adp":                p["adp_ud"],
            "adp_ud":             p["adp_ud"],
            "adp_consensus":      p.get("adp_consensus"),
            "adp_sleeper":        None,
            "adp_espn":           None,
            "adp_yahoo":          None,
            "pos_rank_ud":        p.get("pos_rank_ud"),
            "pos_rank_consensus": p.get("pos_rank_consensus"),
            "pos_rank_sleeper":   p.get("pos_rank_sleeper"),
            "history":            hist,
        })
    return {
        "updated": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "source":  "FantasyPros (Underdog best ball + PPR consensus)",
        "players": out,
    }


def main():
    out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "adp-data.json")

    ud_players     = fetch_fantasypros_bestball()
    consensus_data = fetch_consensus_adp()
    players        = merge_sources(ud_players, consensus_data)

    # SAFETY GUARD: never overwrite with empty data
    if len(players) < 50:
        print("\nERROR: Only " + str(len(players)) + " players fetched — aborting to protect existing data.")
        sys.exit(1)

    existing = load_existing(out_path)
    output   = build_output(players, existing)
    with open(out_path, "w") as f:
        json.dump(output, f, indent=2)
    print("\nSaved " + str(len(players)) + " players to adp-data.json")
    print("Updated: " + output["updated"])


if __name__ == "__main__":
    main()
