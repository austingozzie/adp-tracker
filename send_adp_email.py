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
    window = history[-n:] if len(history) >= n else history
    return sum(s["adp"] for s in window) / len(window)


def get_movers(players, n=10, pos=None, alltime=False, top200=False):
    movers = []
    for p in players:
        if pos and p["pos"] != pos:
            continue
        h = p.get("history", [])
        if len(h) < 2:
            continue

        curr_adp = h[-1]["adp"]
        daily_delta = round(h[-1]["adp"] - h[-2]["adp"], 1)

        if alltime or top200:
            main_delta = round(h[-1]["adp"] - h[0]["adp"], 1)
            days = len(h)
            prev_adp = h[0]["adp"]
        else:
            days_avail = len(h)
            window = min(ROLLING_DAYS, days_avail // 2) if days_avail >= 2 else 1
            recent_avg = rolling_avg(h, window)
            older_avg  = rolling_avg(h[:-window], window) if len(h) > window else h[0]["adp"]
            main_delta = round(recent_avg - older_avg, 1)
            prev_adp   = h[-2]["adp"]
            days = 0

        if main_delta == 0 and daily_delta == 0:
            continue

        if curr_adp > ADP_CUTOFF and prev_adp > ADP_CUTOFF:
            continue

        # For top200, filter to players currently inside top 200
        if top200 and curr_adp > 200:
            continue

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
    h = p.get("history", [])
    adp_ud = p.get("adp_ud") or p.get("adp", 999)

    sl = p.get("adp_sleeper")
    es = p.get("adp_espn")
    if sl and es:
        consensus = (sl + es) / 2
        raw_diff = consensus - adp_ud
        platform_score = max(-10, min(10, raw_diff / 3))
    else:
        platform_score = 0

    if len(h) >= 2:
        window = min(7, len(h) // 2) or 1
        recent = sum(d["adp"] for d in h[-window:]) / window
        older  = sum(d["adp"] for d in h[-window*2:-window]) / window if len(h) >= window * 2 else h[0]["adp"]
        raw_momentum = older - recent
        momentum_score = max(-10, min(10, raw_momentum / 1.5))
    else:
        momentum_score = 0

    if platform_score == 0 and momentum_score == 0:
        return 0
    return round((platform_score + momentum_score) / 2, 1)


def get_top_values(players):
    result = {}
    for pos in POSITIONS:
        pos_players = [p for p in players if p.get("pos") == pos and p.get("adp", 999) <= 200]
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


def value_row(p, score):
    pc = POS_COLORS.get(p["pos"], "#a09890")
    return (
        '<tr style="border-bottom:1px solid #2a2520">'
        '<td style="padding:10px 8px;width:44px">' + badge(p["pos"]) + '</td>'
        '<td style="padding:10px 8px">'
        '<div style="font-weight:600;color:#f0ede8;font-size:13px">' + p["name"] + '</div>'
        '<div style="color:#6b6560;font-size:11px">' + p.get("team","") + ' &middot; ADP ' + str(round(p.get("adp",0),1)) + '</div>'
        '</td>'
        '<td style="padding:10px 8px;text-align:right;font-family:monospace;font-size:15px;font-weight:700;color:#4ade80">+' + str(score) + '</td>'
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

    dr, df   = get_movers(players, 10)
    t2r, t2f = get_movers(players, 10, top200=True)
    ar, af   = get_movers(players, 10, alltime=True)
    days_tracked = max((len(p.get("history", [])) for p in players), default=1)

    body = ""

    # Top value picks
    top_vals = get_top_values(players)
    if top_vals:
        val_rows = ""
        for pos in ["QB","RB","WR","TE"]:
            if pos not in top_vals:
                continue
            score, p = top_vals[pos]
            val_rows += value_row(p, score)
        if val_rows:
            body += label("TOP VALUE PICKS TODAY", "#fbbf24")
            body += table(val_rows)

    # 7-day rolling movers
    if dr or df:
        body += divider("Top Movers — 7-Day Rolling")
        if dr:
            body += label("&#9650; Top " + str(len(dr)) + " Risers", "#4ade80")
            body += table("".join(row(p, True) for p in dr))
        if df:
            body += label("&#9660; Top " + str(len(df)) + " Fallers", "#f87171")
            body += table("".join(row(p, False) for p in df))

    # By position
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

    # Top 200 all-time movers (NEW)
    if t2r or t2f:
        body += divider("Top 200 — Biggest All-Time Movers")
        if t2r:
            body += label("&#9650; Biggest Risers (Inside Top 200)", "#4ade80")
            body += table("".join(row(p, True, True) for p in t2r))
        if t2f:
            body += label("&#9660; Biggest Fallers (Inside Top 200)", "#f87171")
            body += table("".join(row(p, False, True) for p in t2f))

    # All-time
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
        'Data via bestballteambuilder.com / Underdog Fantasy &middot; Updated ' + updated + '</div>'
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
