#!/usr/bin/env python3
“””
send_adp_email.py — Daily ADP digest with:

- Top 10 overall movers (daily)
- Top 5 risers/fallers per position (QB/RB/WR/TE)
- Top 10 movers since app started (all-time)
  “””
  import json, os, smtplib, sys
  from datetime import datetime
  from email.mime.multipart import MIMEMultipart
  from email.mime.text import MIMEText

GMAIL_ADDRESS  = os.environ.get(“GMAIL_ADDRESS”, “”)
GMAIL_APP_PASS = os.environ.get(“GMAIL_APP_PASS”, “”)
SEND_TO        = os.environ.get(“SEND_TO”, “”)
SITE_URL       = os.environ.get(“SITE_URL”, “https://your-site.netlify.app”)
DATA_FILE      = os.path.join(os.path.dirname(os.path.abspath(**file**)), “adp-data.json”)
POS_COLORS     = {“QB”:”#f97316”,“RB”:”#22d3ee”,“WR”:”#a78bfa”,“TE”:”#34d399”}
POSITIONS      = [“QB”,“RB”,“WR”,“TE”]

def load_data():
if not os.path.exists(DATA_FILE):
print(“ERROR: adp-data.json not found.”); sys.exit(1)
with open(DATA_FILE) as f: return json.load(f)

def get_daily_movers(players, n=10, pos=None):
“”“Top movers comparing last 2 snapshots.”””
movers = []
for p in players:
if pos and p[“pos”] != pos: continue
h = p.get(“history”, [])
if len(h) < 2: continue
delta = round(h[-1][“adp”] - h[-2][“adp”], 1)
if delta == 0: continue
movers.append({“name”:p[“name”],“team”:p.get(“team”,””),“pos”:p[“pos”],“adp”:h[-1][“adp”],“delta”:delta})
risers  = sorted([m for m in movers if m[“delta”]<0], key=lambda x:x[“delta”])[:n]
fallers = sorted([m for m in movers if m[“delta”]>0], key=lambda x:-x[“delta”])[:n]
return risers, fallers

def get_alltime_movers(players, n=10):
“”“Top movers comparing first snapshot to latest.”””
movers = []
for p in players:
h = p.get(“history”, [])
if len(h) < 2: continue
delta = round(h[-1][“adp”] - h[0][“adp”], 1)
if delta == 0: continue
movers.append({“name”:p[“name”],“team”:p.get(“team”,””),“pos”:p[“pos”],“adp”:h[-1][“adp”],“delta”:delta,“days”:len(h)})
risers  = sorted([m for m in movers if m[“delta”]<0], key=lambda x:x[“delta”])[:n]
fallers = sorted([m for m in movers if m[“delta”]>0], key=lambda x:-x[“delta”])[:n]
return risers, fallers

def pos_badge(pos):
c = POS_COLORS.get(pos,”#a09890”)
return f’<span style="padding:2px 7px;border-radius:4px;font-size:10px;font-weight:700;background:{c}22;color:{c};font-family:monospace">{pos}</span>’

def player_row(p, is_riser, show_days=False):
arrow = “▲” if is_riser else “▼”
dc    = “#4ade80” if is_riser else “#f87171”
extra = f’<div style="color:#6b6560;font-size:10px">{p.get(“days”,0)}d ago</div>’ if show_days else “”
return f”””<tr style="border-bottom:1px solid #2a2520">
<td style="padding:9px 8px;width:44px">{pos_badge(p[‘pos’])}</td>
<td style="padding:9px 8px">
<div style="font-weight:600;color:#f0ede8;font-size:13px">{p[‘name’]}</div>
<div style="color:#6b6560;font-size:11px">{p[‘team’]}{extra}</div>
</td>
<td style="padding:9px 8px;text-align:right;font-family:monospace;font-size:14px;font-weight:700;color:#f0ede8">{p[‘adp’]:.1f}</td>
<td style="padding:9px 8px;text-align:right;font-family:monospace;font-size:13px;font-weight:700;color:{dc};white-space:nowrap">{arrow} {abs(p[‘delta’])}</td>
</tr>”””

def section(label, color, rows_html):
if not rows_html: return “”
return f”””<div style="margin-bottom:20px">
<div style="font-size:11px;font-weight:700;color:{color};letter-spacing:0.1em;text-transform:uppercase;margin-bottom:8px">{label}</div>
<table style="width:100%;border-collapse:collapse;background:#1a1714;border-radius:12px;overflow:hidden;border:1px solid #2a2520">{rows_html}</table>

  </div>"""

def divider(label):
return f”””<div style="margin:28px 0 16px;display:flex;align-items:center;gap:10px">
<div style="flex:1;height:1px;background:#2a2520"></div>
<div style="font-size:10px;color:#6b6560;font-weight:700;letter-spacing:0.12em;text-transform:uppercase;white-space:nowrap">{label}</div>
<div style="flex:1;height:1px;background:#2a2520"></div>

  </div>"""

def build_html(players, updated):
today = datetime.now().strftime(”%A, %B %-d”)

```
# ── Daily overall
d_risers, d_fallers = get_daily_movers(players, 10)

# ── Daily by position
pos_sections = {}
for pos in POSITIONS:
    pr, pf = get_daily_movers(players, 5, pos=pos)
    pos_sections[pos] = (pr, pf)

# ── All-time
at_risers, at_fallers = get_alltime_movers(players, 10)

has_daily   = d_risers or d_fallers
has_pos     = any(r or f for r,f in pos_sections.values())
has_alltime = at_risers or at_fallers

if not has_daily and not has_alltime:
    return None

body = ""

# ── Section 1: Daily overall
if has_daily:
    body += divider("📈 Today's Top Movers")
    body += section(f"▲ Top {len(d_risers)} Risers", "#4ade80", "".join(player_row(p,True)  for p in d_risers))
    body += section(f"▼ Top {len(d_fallers)} Fallers","#f87171", "".join(player_row(p,False) for p in d_fallers))

# ── Section 2: By position
if has_pos:
    body += divider("🏈 By Position (Top 5)")
    for pos in POSITIONS:
        pr, pf = pos_sections[pos]
        if not pr and not pf: continue
        pc = POS_COLORS[pos]
        body += f'<div style="font-size:12px;font-weight:700;color:{pc};letter-spacing:0.06em;margin:14px 0 6px">{pos}</div>'
        if pr: body += section(f"▲ Risers", "#4ade80", "".join(player_row(p,True)  for p in pr))
        if pf: body += section(f"▼ Fallers","#f87171", "".join(player_row(p,False) for p in pf))

# ── Section 3: All-time
if has_alltime:
    days_tracked = max((len(p.get("history",[])) for p in players), default=1)
    body += divider(f"🏆 All-Time Since Day 1 ({days_tracked} days)")
    body += section(f"▲ Biggest Risers", "#4ade80", "".join(player_row(p,True,True)  for p in at_risers))
    body += section(f"▼ Biggest Fallers","#f87171", "".join(player_row(p,False,True) for p in at_fallers))

return f"""<!DOCTYPE html><html><head><meta charset="UTF-8"/></head>
```

<body style="margin:0;padding:0;background:#0f0d0b;font-family:'Helvetica Neue',Arial,sans-serif">
<div style="max-width:520px;margin:0 auto;padding:24px 16px">
  <div style="margin-bottom:8px">
    <div style="font-size:22px;font-weight:800;color:#f0ede8;letter-spacing:-0.5px">ADP<span style="color:#f97316">°</span>TRACKER</div>
    <div style="font-size:11px;color:#6b6560;letter-spacing:0.08em;margin-top:2px">UNDERDOG FANTASY · NFL BEST BALL · {today.upper()}</div>
  </div>
  {body}
  <div style="text-align:center;margin:28px 0 20px">
    <a href="{SITE_URL}" style="display:inline-block;background:#f97316;color:#0f0d0b;font-weight:700;font-size:14px;padding:14px 32px;border-radius:10px;text-decoration:none">View Full ADP Tracker →</a>
  </div>
  <div style="font-size:11px;color:#4a4540;text-align:center;border-top:1px solid #2a2520;padding-top:16px">Data via FantasyPros / Underdog Fantasy · Updated {updated}</div>
</div></body></html>"""

def send_email(html, d_risers, d_fallers):
if not GMAIL_ADDRESS or not GMAIL_APP_PASS or not SEND_TO:
print(“ERROR: Missing email env vars.”); sys.exit(1)
today      = datetime.now().strftime(”%b %-d”)
top_riser  = d_risers[0][“name”]  if d_risers  else “—”
top_faller = d_fallers[0][“name”] if d_fallers else “—”
subject    = f”ADP° Daily Movers {today} — ▲ {top_riser} · ▼ {top_faller}”
msg = MIMEMultipart(“alternative”)
msg[“Subject”] = subject; msg[“From”] = GMAIL_ADDRESS; msg[“To”] = SEND_TO
msg.attach(MIMEText(html, “html”))
print(f”Sending to {SEND_TO}…”)
with smtplib.SMTP_SSL(“smtp.gmail.com”, 465) as s:
s.login(GMAIL_ADDRESS, GMAIL_APP_PASS)
s.sendmail(GMAIL_ADDRESS, SEND_TO, msg.as_string())
print(“✅ Email sent!”)

def main():
data    = load_data()
players = data.get(“players”, [])
updated = data.get(“updated”, “”)
print(f”Loaded {len(players)} players.”)

```
d_risers, d_fallers = get_daily_movers(players, 10)
print(f"Daily: {len(d_risers)} risers, {len(d_fallers)} fallers")

html = build_html(players, updated)
if not html:
    print("No movers yet — needs 2+ days of data."); sys.exit(0)

send_email(html, d_risers, d_fallers)
```

if **name** == “**main**”: main()
