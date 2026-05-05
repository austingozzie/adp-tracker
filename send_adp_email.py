#!/usr/bin/env python3
"""
send_adp_email.py — reads config from environment variables (GitHub Secrets)
"""
import json, os, smtplib, sys
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

GMAIL_ADDRESS  = os.environ.get("GMAIL_ADDRESS", "")
GMAIL_APP_PASS = os.environ.get("GMAIL_APP_PASS", "")
SEND_TO        = os.environ.get("SEND_TO", "")
SITE_URL       = os.environ.get("SITE_URL", "https://your-site.netlify.app")
DATA_FILE      = os.path.join(os.path.dirname(os.path.abspath(__file__)), "adp-data.json")
POS_COLORS     = {"QB":"#f97316","RB":"#22d3ee","WR":"#a78bfa","TE":"#34d399"}

def load_data():
    if not os.path.exists(DATA_FILE):
        print("ERROR: adp-data.json not found."); sys.exit(1)
    with open(DATA_FILE) as f: return json.load(f)

def get_movers(players, n=10):
    movers = []
    for p in players:
        h = p.get("history", [])
        if len(h) < 2: continue
        delta = round(h[-1]["adp"] - h[-2]["adp"], 1)
        if delta == 0: continue
        movers.append({"name":p["name"],"team":p.get("team",""),"pos":p["pos"],"adp":h[-1]["adp"],"delta":delta})
    risers  = sorted([m for m in movers if m["delta"]<0], key=lambda x:x["delta"])[:n]
    fallers = sorted([m for m in movers if m["delta"]>0], key=lambda x:-x["delta"])[:n]
    return risers, fallers

def pos_badge(pos):
    c = POS_COLORS.get(pos,"#a09890")
    return f'<span style="padding:2px 7px;border-radius:4px;font-size:10px;font-weight:700;background:{c}22;color:{c};font-family:monospace">{pos}</span>'

def player_row(p, is_riser):
    arrow = "▲" if is_riser else "▼"
    dc    = "#4ade80" if is_riser else "#f87171"
    return f"""<tr style="border-bottom:1px solid #2a2520">
      <td style="padding:10px 8px;width:44px">{pos_badge(p['pos'])}</td>
      <td style="padding:10px 8px">
        <div style="font-weight:600;color:#f0ede8;font-size:14px">{p['name']}</div>
        <div style="color:#6b6560;font-size:11px">{p['team']}</div>
      </td>
      <td style="padding:10px 8px;text-align:right;font-family:monospace;font-size:15px;font-weight:700;color:#f0ede8">{p['adp']:.1f}</td>
      <td style="padding:10px 8px;text-align:right;font-family:monospace;font-size:13px;font-weight:700;color:{dc}">{arrow} {abs(p['delta'])}</td>
    </tr>"""

def build_html(risers, fallers, updated):
    today = datetime.now().strftime("%A, %B %-d")
    rr = "".join(player_row(p,True)  for p in risers)
    fr = "".join(player_row(p,False) for p in fallers)
    return f"""<!DOCTYPE html><html><head><meta charset="UTF-8"/></head>
<body style="margin:0;padding:0;background:#0f0d0b;font-family:'Helvetica Neue',Arial,sans-serif">
<div style="max-width:520px;margin:0 auto;padding:24px 16px">
  <div style="margin-bottom:24px">
    <div style="font-size:22px;font-weight:800;color:#f0ede8">ADP<span style="color:#f97316">°</span>TRACKER</div>
    <div style="font-size:11px;color:#6b6560;letter-spacing:0.08em;margin-top:2px">UNDERDOG FANTASY · NFL BEST BALL · {today.upper()}</div>
  </div>
  <div style="margin-bottom:24px">
    <div style="font-size:11px;font-weight:700;color:#4ade80;letter-spacing:0.1em;text-transform:uppercase;margin-bottom:10px">▲ Top {len(risers)} Risers</div>
    <table style="width:100%;border-collapse:collapse;background:#1a1714;border-radius:12px;overflow:hidden;border:1px solid #2a2520">{rr}</table>
  </div>
  <div style="margin-bottom:32px">
    <div style="font-size:11px;font-weight:700;color:#f87171;letter-spacing:0.1em;text-transform:uppercase;margin-bottom:10px">▼ Top {len(fallers)} Fallers</div>
    <table style="width:100%;border-collapse:collapse;background:#1a1714;border-radius:12px;overflow:hidden;border:1px solid #2a2520">{fr}</table>
  </div>
  <div style="text-align:center;margin-bottom:24px">
    <a href="{SITE_URL}" style="display:inline-block;background:#f97316;color:#0f0d0b;font-weight:700;font-size:14px;padding:14px 32px;border-radius:10px;text-decoration:none">View Full ADP Tracker →</a>
  </div>
  <div style="font-size:11px;color:#4a4540;text-align:center;border-top:1px solid #2a2520;padding-top:16px">Data via FantasyPros / Underdog Fantasy · Updated {updated}</div>
</div></body></html>"""

def send_email(html, risers, fallers):
    if not GMAIL_ADDRESS or not GMAIL_APP_PASS or not SEND_TO:
        print("ERROR: Missing email env vars."); sys.exit(1)
    today = datetime.now().strftime("%b %-d")
    subject = f"ADP° Daily Movers {today} — ▲ {risers[0]['name'] if risers else '—'} · ▼ {fallers[0]['name'] if fallers else '—'}"
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject; msg["From"] = GMAIL_ADDRESS; msg["To"] = SEND_TO
    msg.attach(MIMEText(html, "html"))
    print(f"Sending to {SEND_TO}...")
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as s:
        s.login(GMAIL_ADDRESS, GMAIL_APP_PASS)
        s.sendmail(GMAIL_ADDRESS, SEND_TO, msg.as_string())
    print("✅ Email sent!")

def main():
    data    = load_data()
    players = data.get("players", [])
    updated = data.get("updated", "")
    print(f"Loaded {len(players)} players.")
    risers, fallers = get_movers(players)
    print(f"{len(risers)} risers, {len(fallers)} fallers")
    if not risers and not fallers:
        print("No movers yet — needs 2+ days of data."); sys.exit(0)
    send_email(build_html(risers, fallers, updated), risers, fallers)

if __name__ == "__main__": main()
