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


def fetch_adp_data():
    """Fetch Underdog ADP from bestballteambuilder.com — server-rendered HTML table."""
    print("Fetching Underdog ADP from bestballteambuilder.com...")
    url = "https://www.bestballteambuilder.com/underdog-best-ball-average-draft-position"
    resp = requests.get(url, headers=HEADERS, timeout=20)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    tables = soup.find_all("table")
    print("  Found " + str(len(tables)) + " tables")

    players = {}
    seen_names = set()

    for table in tables:
        thead = table.find("thead")
        if not thead:
            continue
        headers = [th.get_text(strip=True).lower() for th in thead.find_all("th")]

        name_idx    = next((i for i, h in enumerate(headers) if "player" in h), 0)
        pos_idx     = next((i for i, h in enumerate(headers) if h in ("position", "pos")), None)
        team_idx    = next((i for i, h in enumerate(headers) if h == "team"), None)
        adp_idx     = next((i for i, h in enumerate(headers) if h == "adp"), None)

        if adp_idx is None:
            continue

        tbody = table.find("tbody")
        rows = tbody.find_all("tr") if tbody else table.find_all("tr")[1:]
        for row in rows:
            cells = row.find_all("td")
            if len(cells) <= adp_idx:
                continue

            name = cells[name_idx].get_text(strip=True) if name_idx < len(cells) else ""
            if not name or name in seen_names:
                continue

            pos  = cells[pos_idx].get_text(strip=True).upper() if pos_idx is not None and pos_idx < len(cells) else ""
            team = cells[team_idx].get_text(strip=True).upper() if team_idx is not None and team_idx < len(cells) else ""

            if pos not in VALID_POS:
                continue

            adp_text = cells[adp_idx].get_text(strip=True)
            try:
                adp_val = float(adp_text)
            except ValueError:
                continue
            if adp_val <= 0:
                continue

            seen_names.add(name)
            key = name + "|" + pos
            players[key] = {"name": name, "team": team, "pos": pos, "adp_ud": adp_val}

    print("  Found " + str(len(players)) + " Underdog players")
    return players


def fetch_consensus_adp():
    """Fetch half-PPR consensus ADP from Fantasy Football Calculator free API."""
    print("Fetching consensus ADP from Fantasy Football Calculator API...")
    url = "https://fantasyfootballcalculator.com/api/v1/adp/ppr?teams=12&year=2026"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        print("  WARNING: Could not fetch FFC ADP: " + str(e))
        return {}

    players_raw = data.get("players", [])
    print("  Got " + str(len(players_raw)) + " players from FFC")

    result = {}
    for p in players_raw:
        name = p.get("name", "").strip()
        pos  = p.get("position", "").strip().upper()
        adp  = p.get("adp")
        if not name or pos not in VALID_POS or not adp:
            continue
        try:
            adp_val = float(adp)
        except (TypeError, ValueError):
            continue
        if adp_val <= 0:
            continue
        result[name + "|" + pos] = adp_val

    print("  Found " + str(len(result)) + " consensus ADP values")
    return result


def norm(name):
    name = re.sub(r"\b(jr|sr|ii|iii|iv)\.?\b", "", name.lower().strip())
    name = re.sub(r"[^a-z ]", "", name)
    name = re.sub(r"\s+", " ", name).strip()
    return name


def merge_sources(ud_players, consensus_data):
    cons_norm = {}
    for key, val in consensus_data.items():
        parts = key.rsplit("|", 1)
        if len(parts) == 2:
            cons_norm[norm(parts[0]) + "|" + parts[1]] = val

    # First-initial + last name fallback
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
            "name":          name,
            "team":          p["team"],
            "pos":           pos,
            "adp":           p["adp_ud"],
            "adp_ud":        p["adp_ud"],
            "adp_consensus": adp_cons,
            "adp_sleeper":   None,
            "adp_espn":      None,
            "adp_yahoo":     None,
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
        "source":  "bestballteambuilder.com (Underdog) + FantasyFootballCalculator (half-PPR consensus)",
        "players": out,
    }


def main():
    out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "adp-data.json")

    ud_players     = fetch_adp_data()
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
