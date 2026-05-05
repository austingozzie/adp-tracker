#!/usr/bin/env python3
"""
fetch_adp.py
------------
Fetches Underdog Fantasy ADP from FantasyPros and saves it to adp-data.json
in the same folder. Run this script whenever you want fresh ADP data.

Usage:
    python3 fetch_adp.py

Requirements:
    pip install requests beautifulsoup4
"""

import json
import re
import sys
import os
from datetime import datetime

try:
    import requests
    from bs4 import BeautifulSoup
except ImportError:
    print("Installing required packages...")
    os.system(f"{sys.executable} -m pip install requests beautifulsoup4 -q")
    import requests
    from bs4 import BeautifulSoup

URL = "https://www.fantasypros.com/nfl/adp/best-ball-overall.php"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}

VALID_POS = {"QB", "RB", "WR", "TE"}

def fetch_players():
    print(f"Fetching ADP from FantasyPros...")
    resp = requests.get(URL, headers=HEADERS, timeout=15)
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "html.parser")
    table = soup.find("table")
    if not table:
        raise ValueError("Could not find ADP table on page")

    # Find column index for "Underdog"
    header_row = table.find("thead")
    headers = [th.get_text(strip=True) for th in header_row.find_all("th")] if header_row else []
    print(f"  Columns: {headers}")

    # Underdog is typically index 5 (0-based), but let's find it dynamically
    ud_idx = None
    for i, h in enumerate(headers):
        if "underdog" in h.lower():
            ud_idx = i
            break
    if ud_idx is None:
        # fallback: col 5
        ud_idx = 5
    print(f"  Underdog column index: {ud_idx}")

    players = []
    tbody = table.find("tbody")
    rows = tbody.find_all("tr") if tbody else table.find_all("tr")[1:]

    for row in rows:
        cells = row.find_all("td")
        if len(cells) < ud_idx + 1:
            continue

        # Name + team cell (index 1)
        name_cell = cells[1]
        name_text = name_cell.get_text(separator=" ", strip=True)

        # Position cell (index 2)
        pos_text = cells[2].get_text(strip=True) if len(cells) > 2 else ""
        pos = re.sub(r"\d+$", "", pos_text).strip()  # strip positional rank

        # Underdog ADP
        ud_text = cells[ud_idx].get_text(strip=True)
        try:
            ud_adp = float(ud_text)
        except ValueError:
            continue  # skip if no Underdog ADP (blank)

        if ud_adp <= 0:
            continue

        if pos not in VALID_POS:
            continue

        # Parse name and team from name_cell
        # Format is usually "Player Name TEAM" e.g. "Bijan Robinson ATL"
        parts = name_text.split()
        if len(parts) >= 2 and re.match(r"^[A-Z]{2,4}$", parts[-1]):
            team = parts[-1]
            name = " ".join(parts[:-1])
        else:
            team = ""
            name = name_text

        players.append({
            "name": name,
            "team": team,
            "pos": pos,
            "adp": ud_adp,
        })

    return players


def load_existing(path):
    """Load existing adp-data.json to preserve historical snapshots."""
    if not os.path.exists(path):
        return {}
    with open(path, "r") as f:
        data = json.load(f)
    # Convert list to dict keyed by "Name|Team|Pos"
    existing = {}
    for p in data.get("players", []):
        key = f"{p['name']}|{p['team']}|{p['pos']}"
        existing[key] = p
    return existing


def build_output(players, existing):
    today = datetime.now().strftime("%b %-d")  # e.g. "May 4"
    output_players = []

    for p in players:
        key = f"{p['name']}|{p['team']}|{p['pos']}"
        prev = existing.get(key, {})
        history = prev.get("history", [])

        # Append today's snapshot if it's a new date or no history yet
        if not history or history[-1]["date"] != today:
            history.append({"date": today, "adp": p["adp"]})

        # Keep last 30 days of history
        history = history[-30:]

        output_players.append({
            "name": p["name"],
            "team": p["team"],
            "pos": p["pos"],
            "adp": p["adp"],
            "history": history,
        })

    return {
        "updated": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "source": "FantasyPros / Underdog Fantasy",
        "players": output_players,
    }


def main():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    out_path = os.path.join(script_dir, "adp-data.json")

    players = fetch_players()
    print(f"  Parsed {len(players)} players with Underdog ADP")

    existing = load_existing(out_path)
    output = build_output(players, existing)

    with open(out_path, "w") as f:
        json.dump(output, f, indent=2)

    print(f"\n✅ Saved {len(players)} players to adp-data.json")
    print(f"   Updated: {output['updated']}")
    print(f"\nNow open adp-tracker.html in your browser.")


if __name__ == "__main__":
    main()
