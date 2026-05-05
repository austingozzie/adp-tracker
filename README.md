# ADP° Tracker — Setup Guide

## What this does
- Fetches live Underdog Fantasy ADP from FantasyPros every day
- Hosts a full ADP tracker website (free on Netlify)
- Emails you the top 10 risers and fallers every morning at 8am

---

## Step 1 — Create a GitHub account
Go to https://github.com and sign up (free).

---

## Step 2 — Create a new repository
1. Click the **+** icon → **New repository**
2. Name it: `adp-tracker`
3. Set it to **Public**
4. Click **Create repository**

---

## Step 3 — Upload these files to GitHub
On your new repo page, click **uploading an existing file** and drag in:
- `index.html`
- `fetch_adp.py`
- `send_adp_email.py`
- `.github/workflows/daily-adp.yml`

Click **Commit changes**.

---

## Step 4 — Add your secrets to GitHub
Go to your repo → **Settings** → **Secrets and variables** → **Actions** → **New repository secret**

Add these 4 secrets:

| Name | Value |
|------|-------|
| `GMAIL_ADDRESS` | your Gmail address |
| `GMAIL_APP_PASS` | your Gmail App Password (see below) |
| `SEND_TO` | email you want to receive the digest |
| `SITE_URL` | your Netlify URL (add this after Step 6) |

### How to get a Gmail App Password
1. Go to https://myaccount.google.com/apppasswords
2. Sign in, click **Create App Password**
3. Name it "ADP Tracker" and copy the 16-character password
4. Paste it as the `GMAIL_APP_PASS` secret

---

## Step 5 — Deploy to Netlify
1. Go to https://netlify.com and sign up (free)
2. Click **Add new site** → **Import an existing project** → **GitHub**
3. Select your `adp-tracker` repo
4. Leave all settings as default → click **Deploy site**
5. Netlify gives you a URL like `https://adp-tracker-abc123.netlify.app`
6. Copy that URL and add it as the `SITE_URL` secret in GitHub (Step 4)

---

## Step 6 — Run the first fetch manually
1. In your GitHub repo, click **Actions**
2. Click **Daily ADP Update** on the left
3. Click **Run workflow** → **Run workflow**

This fetches today's ADP data and commits `adp-data.json` to your repo.
Netlify will auto-redeploy with the new data — your site is live!

---

## Done!
- Your site is live at your Netlify URL
- Every day at 8am an email arrives with the top movers
- Each daily run adds a new data point, building up real historical trend charts over time
