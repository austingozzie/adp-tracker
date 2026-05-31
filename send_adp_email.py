import json, os, smtplib, sys
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

GMAIL_ADDRESS  = os.environ.get("GMAIL_ADDRESS", "")
GMAIL_APP_PASS = os.environ.get("GMAIL_APP_PASS", "")
SEND_TO        = os.environ.get("SEND_TO", "")
SITE_URL       = os.environ.get("SITE_URL", "https://your-site.netlify.app")
DATA_FILE      = os.path.join(os.path.dirname(os.path.abspath(__file__)), "adp-data.json")
POS_COLORS     = {"QB": "#f97316", "RB": "#22d3ee", "WR": "#a78bfa", "TE": "#34d399"}
POSITIONS      = ["QB", "RB", "WR", "TE"]
ADP_CUTOFF     = 250
ROLLING_DAYS   = 7


def load_data():
    if not os.path.exists(DATA_FILE):
        print("ERROR: adp-data.json not found.")
        sys.exit(1)
    with open(DATA_FILE) as f:
        return json.load(f)


def rolling_avg(history, n):
    # Average the last n snapshots, or however many exist
    window = history[-n:] if len(history) >= n else history
    return sum(s["adp"] for s in window) / len(window)


def get_movers(players, n=10, pos=None, alltime=False):
    movers = []
    for p in players:
        if pos and p["pos"] != pos:
            continue
        h = p.get("history", [])
        if len(h) < 2:
            continue

        curr_adp = h[-1]["adp"]
        daily_delta = round(h[-1]["adp"] - h[-2]["adp"], 1)

        if alltime:
            main_delta = round(h[-1]["adp"] - h[0]["adp"], 1)
            days = len(h)
            prev_adp = h[0]["adp"]
        else:
            # 7-day rolling: compare avg of last 7 days vs avg of 7 days before that
            days_avail = len(h)
            window = min(ROLLING_DAYS, days_avail // 2) if days_avail >= 2 else 1
            recent_avg = rolling_avg(h, window)
            older_avg  = rolling_avg(h[:-window], window) if len(h) > window else h[0]["adp"]
            main_delta = round(recent_avg - older_avg, 1)
            prev_adp   = h[-2]["adp"]
            days = 0

        if main_delta == 0 and daily_delta == 0:
            continue

        # Only include players within top 250 or crossing the threshold
        if curr_adp > ADP_CUTOFF and prev_adp > ADP_CUTOFF:
            continue

        # Flag if today reverses the rolling trend
        reversal = (main_delta < 0 and daily_delta > 0) or (main_delta > 0 and daily_delta < 0)

        movers.append({
            "name": p["name"],
            "team": p.get("team", ""),
            "pos": p["pos"],
            "adp": curr_adp,
            "delta": main_delta,
            "daily": daily_delta,
            "days": days,
            "reversal": reversal,
        })

    risers  = sorted([m for m in movers if m["delta"] < 0], key=lambda x: x["delta"])[:n]
    fallers = sorted([m for m in movers if m["delta"] > 0], key=lambda x: -x["delta"])[:n]
    return risers, fallers


def calc_value_score(p):
    """
    Equal mix of platform discount and momentum.
    Higher score = better value to draft today.
    """
    h = p.get("history", [])
    adp_ud = p.get("adp_ud") or p.get("adp", 999)

    # 1. Platform discount (avg of available platform ADPs vs Underdog)
    others = [v for v in [p.get("adp_sleeper"), p.get("adp_espn")] if v]
    if others:
        consensus = sum(others) / len(others)
        # Positive = Underdog drafts him earlier (higher ADP number on other platforms = value on UD)
        platform_score = consensus - adp_ud
    else:
        platform_score = 0

    # 2. Momentum score (7-day rolling change, dropping ADP = positive)
    if len(h) >= 2:
        window = min(7, len(h) // 2) or 1
        recent = sum(d["adp"] for d in h[-window:]) / window
        older  = sum(d["adp"] for d in h[-window*2:-window]) / window if len(h) >= window * 2 else h[0]["adp"]
        momentum_score = older - recent  # positive = ADP dropped = rising stock
    else:
        momentum_score = 0

    # Equal mix
    return round((platform_score + momentum_score) / 2, 1)


def get_top_values(players):
    """Get best value player per position."""
    POSITIONS = ["QB", "RB", "WR", "TE"]
    result = {}
    for pos in POSITIONS:
        pos_players = [p for p in players if p.get("pos") == pos and p.get("adp", 999) <= ADP_CUTOFF]
        if not pos_players:
            continue
        scored = []
        for p in pos_players:
            score = calc_value_score(p)
            if score > 0:
                scored.append((score, p))
        if scored:
            scored.sort(key=lambda x: -x[0])
            result[pos] = (scored[0][0], scored[0][1])
    return result


def badge(pos):
    c = POS_COLORS.get(pos, "#999")
    return (
        '<span style="padding:2px 7px;border-radius:4px;font-size:10px;'
        'font-weight:700;background:' + c + '22;color:' + c + ';font-family:monospace">'
        + pos + '</span>'
    )


def row(p, up, show_days=False):
    dc  = "#4ade80" if up else "#f87171"
    ar  = "&#9650;" if up else "&#9660;"

    # Daily change indicator
    if p.get("daily", 0) != 0:
        d_up   = p["daily"] < 0
        d_col  = "#4ade80" if d_up else "#f87171"
        d_ar   = "&#9650;" if d_up else "&#9660;"
        d_warn = " &#9888;" if p.get("reversal") else ""
        daily_str = (
            '<span style="font-size:10px;color:' + d_col + ';margin-left:6px">'
            + d_ar + ' ' + str(abs(p["daily"])) + ' today' + d_warn + '</span>'
        )
    else:
        daily_str = ""

    days_str = ""
    if show_days and p.get("days"):
        days_str = '<div style="color:#6b6560;font-size:10px">' + str(p["days"]) + ' days</div>'

    rolling_label = "" if show_days else '<span style="color:#6b6560;font-size:10px;margin-left:4px">7d</span>'

    return (
        '<tr style="border-bottom:1px solid #2a2520">'
        '<td style="padding:9px 8px;width:44px">' + badge(p["pos"]) + '</td>'
        '<td style="padding:9px 8px">'
        '<div style="font-weight:600;color:#f0ede8;font-size:13px">' + p["name"] + '</div>'
        '<div style="color:#6b6560;font-size:11px">' + p["team"] + days_str + '</div>'
        '</td>'
        '<td style="padding:9px 8px;text-align:right;font-family:monospace;font-size:13px;font-weight:700;color:#f0ede8">'
        + str(round(p["adp"], 1)) +
        '</td>'
        '<td style="padding:9px 6px;text-align:right;font-family:monospace;font-size:12px;font-weight:700">'
        '<div style="color:' + dc + '">' + ar + ' ' + str(abs(p["delta"])) + rolling_label + '</div>'
        '<div>' + daily_str + '</div>'
        '</td>'
        '</tr>'
    )


def table(rows_html):
    return (
        '<table style="width:100%;border-collapse:collapse;background:#1a1714;'
        'border-radius:12px;overflow:hidden;border:1px solid #2a2520">'
        + rows_html + '</table>'
    )


def label(text, color):
    return (
        '<div style="font-size:11px;font-weight:700;color:' + color + ';'
        'letter-spacing:0.1em;text-transform:uppercase;margin-bottom:8px;margin-top:16px">'
        + text + '</div>'
    )


def divider(text):
    return (
        '<div style="margin:24px 0 8px;text-align:center;font-size:10px;'
        'color:#6b6560;font-weight:700;letter-spacing:0.12em;text-transform:uppercase;'
        'border-top:1px solid #2a2520;padding-top:16px">' + text + '</div>'
    )


def build_html(players, updated):
    today = datetime.now().strftime("%A, %B %d").replace(" 0", " ")

    dr, df = get_movers(players, 10)
    ar, af = get_movers(players, 10, alltime=True)
    days_tracked = max((len(p.get("history", [])) for p in players), default=1)

    body = ""

    # Top value picks section
    top_vals = get_top_values(players)
    if top_vals:
        pos_colors = {"QB":"#f97316","RB":"#22d3ee","WR":"#a78bfa","TE":"#34d399"}
        val_rows = ""
        for pos in ["QB","RB","WR","TE"]:
            if pos not in top_vals:
                continue
            score, p = top_vals[pos]
            pc = pos_colors.get(pos, "#a09890")
            val_rows += (
                '<tr style="border-bottom:1px solid #2a2520">'
                '<td style="padding:10px 8px;width:44px">'
                '<span style="padding:2px 7px;border-radius:4px;font-size:10px;font-weight:700;'
                'background:' + pc + '22;color:' + pc + ';font-family:monospace">' + pos + '</span>'
                '</td>'
                '<td style="padding:10px 8px">'
                '<div style="font-weight:600;color:#f0ede8;font-size:13px">' + p["name"] + '</div>'
                '<div style="color:#6b6560;font-size:11px">' + p.get("team","") + ' &middot; ADP ' + str(round(p.get("adp",0),1)) + '</div>'
                '</td>'
                '<td style="padding:10px 8px;text-align:right;font-family:monospace;font-size:14px;font-weight:700;color:#4ade80">'
                '+' + str(score)
                '</td>'
                '</tr>'
            )
        body += (
            '<div style="margin-bottom:20px">'
            '<div style="font-size:11px;font-weight:700;color:#fbbf24;letter-spacing:0.1em;'
            'text-transform:uppercase;margin-bottom:8px">&#127919; Today's Top Value Picks</div>'
            '<table style="width:100%;border-collapse:collapse;background:#1a1714;'
            'border-radius:12px;overflow:hidden;border:1px solid #2a2520">' + val_rows + '</table>'
            '<div style="font-size:10px;color:#4a4540;margin-top:6px;padding-left:2px">'
            'Score = platform discount + momentum (higher = better value on Underdog)</div>'
            '</div>'
        )

    if dr or df:
        body += divider("Top Movers — 7-Day Rolling")
        if dr:
            body += label("&#9650; Top " + str(len(dr)) + " Risers", "#4ade80")
            body += table("".join(row(p, True) for p in dr))
        if df:
            body += label("&#9660; Top " + str(len(df)) + " Fallers", "#f87171")
            body += table("".join(row(p, False) for p in df))

    body += divider("By Position — Top 5 (7-Day Rolling)")
    for pos in POSITIONS:
        pr, pf = get_movers(players, 5, pos=pos)
        if not pr and not pf:
            continue
        pc = POS_COLORS[pos]
        body += '<div style="font-size:12px;font-weight:700;color:' + pc + ';margin:14px 0 4px">' + pos + '</div>'
        if pr:
            body += label("&#9650; Risers", "#4ade80")
            body += table("".join(row(p, True) for p in pr))
        if pf:
            body += label("&#9660; Fallers", "#f87171")
            body += table("".join(row(p, False) for p in pf))

    if ar or af:
        body += divider("All-Time Since Day 1 (" + str(days_tracked) + " days)")
        if ar:
            body += label("&#9650; Biggest Risers", "#4ade80")
            body += table("".join(row(p, True, True) for p in ar))
        if af:
            body += label("&#9660; Biggest Fallers", "#f87171")
            body += table("".join(row(p, False, True) for p in af))

    body += (
        '<div style="margin-top:16px;font-size:10px;color:#4a4540;text-align:center">'
        '&#9888; = today reversing 7-day trend &nbsp;|&nbsp; 7d = 7-day rolling change'
        '</div>'
    )

    if not body:
        return None

    return (
        '<!DOCTYPE html><html><head><meta charset="UTF-8"/></head>'
        '<body style="margin:0;padding:0;background:#0f0d0b;font-family:Helvetica Neue,Arial,sans-serif">'
        '<div style="max-width:520px;margin:0 auto;padding:24px 16px">'
        '<div style="margin-bottom:8px">'
        '<div style="font-size:22px;font-weight:800;color:#f0ede8;letter-spacing:-0.5px">'
        'ADP<span style="color:#f97316">&#176;</span>TRACKER</div>'
        '<div style="font-size:11px;color:#6b6560;letter-spacing:0.08em;margin-top:2px">'
        'UNDERDOG FANTASY &middot; NFL BEST BALL &middot; ' + today.upper() + '</div>'
        '</div>'
        + body +
        '<div style="text-align:center;margin:28px 0 20px">'
        '<a href="' + SITE_URL + '" style="display:inline-block;background:#f97316;'
        'color:#0f0d0b;font-weight:700;font-size:14px;padding:14px 32px;'
        'border-radius:10px;text-decoration:none">View Full ADP Tracker &#8594;</a>'
        '</div>'
        '<div style="font-size:11px;color:#4a4540;text-align:center;'
        'border-top:1px solid #2a2520;padding-top:16px">'
        'Data via FantasyPros / Underdog Fantasy &middot; Updated ' + updated + '</div>'
        '</div></body></html>'
    )


def send_email(html, dr, df):
    if not GMAIL_ADDRESS or not GMAIL_APP_PASS or not SEND_TO:
        print("ERROR: Missing email env vars.")
        sys.exit(1)
    today = datetime.now().strftime("%b %d").replace(" 0", " ")
    top_r = dr[0]["name"] if dr else "---"
    top_f = df[0]["name"] if df else "---"
    subject = "ADP Daily Movers " + today + " -- Up: " + top_r + " | Dn: " + top_f
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = GMAIL_ADDRESS
    msg["To"] = SEND_TO
    msg.attach(MIMEText(html, "html"))
    print("Sending to " + SEND_TO + "...")
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as s:
        s.login(GMAIL_ADDRESS, GMAIL_APP_PASS)
        s.sendmail(GMAIL_ADDRESS, SEND_TO, msg.as_string())
    print("Email sent!")


def main():
    data = load_data()
    players = data.get("players", [])
    updated = data.get("updated", "")
    print("Loaded " + str(len(players)) + " players.")
    dr, df = get_movers(players, 10)
    print(str(len(dr)) + " risers, " + str(len(df)) + " fallers")
    html = build_html(players, updated)
    if not html:
        print("No movers yet -- needs 2+ days of data.")
        sys.exit(0)
    send_email(html, dr, df)


if __name__ == "__main__":
    main()
