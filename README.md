# Garmin Daily AI Insights

**Free daily AI brief on your Garmin data — Gemini reads your full history, push to your phone. $0 to run.**

Fully automated pipeline: pull Garmin Connect into SQLite, send formatted daily history to Gemini for analysis, and deliver a short coached brief via ntfy, Telegram, or email. Runs on GitHub Actions; no server to maintain.



*Example notification layout — your numbers and wording change daily.*

## What you get each morning

```
WATCH
• Stress 34 vs 30d avg 23 — worsening
• Sleep 6.15h — under 7h target

WINS
• Intensity 63 min — all-time high
• Resting HR improving, 2-day streak near ATL

TODAY
In bed 30 minutes earlier tonight.

—
Poor sleep raises cortisol and daily stress.
```

**Cost:** $0 (Garmin via `garminconnect`, Gemini free tier, GitHub Actions, ntfy/Telegram/email).

## Setup

### 1. Python environment

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Mint Garmin token (local, once)

```bash
python scripts/mint_token.py
```

Use your Garmin email, password, and MFA code. Tokens are saved to `~/.garminconnect` (valid ~1 year).

### 3. Backfill history

```bash
BACKFILL_DAYS=180 python -m src.backfill
```

Creates `garmin.db`. Commit it to your repo after backfill completes (re-run backfill after schema changes to refresh columns).

### 4. GitHub Actions secrets

Package tokens for CI:

```bash
bash scripts/pack_tokens.sh
```

Copy the **single long line** of output into repository secret `GARMIN_TOKENS_B64` (no quotes, no spaces, no line breaks in the secret value).

If Actions fails with `base64: invalid input`, the secret was pasted wrong — re-run `pack_tokens.sh` and replace the secret entirely.

Manual alternative:

```bash
tar -cf tokens.tar -C ~/.garminconnect .
base64 < tokens.tar | tr -d '\n\r '
# paste that one line into GARMIN_TOKENS_B64
rm -f tokens.tar
```


| Secret                                           | Purpose                                         |
| ------------------------------------------------ | ----------------------------------------------- |
| `GARMIN_TOKENS_B64`                              | base64 tar of `~/.garminconnect`                |
| `GEMINI_API_KEY`                                 | [Google AI Studio](https://aistudio.google.com) |
| `NOTIFIER`                                       | `ntfy` (default), `telegram`, or `email`        |
| `NTFY_TOPIC`                                     | long random topic (ntfy)                        |
| `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID`        | Telegram                                        |
| `EMAIL_USER` / `EMAIL_APP_PASSWORD` / `EMAIL_TO` | Gmail app password                              |


### 5. Notifier

**ntfy (default):** Install the [ntfy app](https://ntfy.sh), subscribe to a long random topic, set `NTFY_TOPIC`.

**Telegram:** Create a bot via @BotFather, get your chat id.

**Email:** Gmail app password (not account password).

### 6. Test locally

```bash
cp .env.example .env   # fill in secrets
python -m src.main
```

### 7. Deploy

Create a GitHub repo, commit everything including `garmin.db`, add secrets, run **workflow_dispatch** on `garmin-daily` once to verify CI. The repo can be **public** if you accept that `garmin.db` exposes daily health numbers (see below).

## What goes in `garmin.db` (public-safe design)

Only **scalar daily wellness metrics** are stored. There is **no `raw` JSON**, no GPS, no activity routes, no maps, and no activity list/workout details.


| Stored                                                                                                                                   | Not stored                                 |
| ---------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------ |
| Steps, resting HR, sleep (duration/score/stages), stress, Body Battery high/low, HRV, training readiness, intensity minutes, active kcal | Location, lat/long, track polyline         |
| SpO2, VO2 max, Garmin **fitness age**, weight (g), body fat %                                                                            | Activity names, routes, timestamps per lap |
| Date (`YYYY-MM-DD`) only                                                                                                                 | Full API responses, heart-rate streams     |


**Fitness age** is Garmin’s estimated fitness age (a single number), not your birthdate or home address.

## Daily run

`python -m src.main` — pull recent days → format full history → Gemini brief → notification.

GitHub Actions runs at **11:00 UTC** (~7:00 AM US Eastern in EDT; ~6:00 AM in EST), commits updated `garmin.db`, and pushes.

## Gotchas

- **Cron drift:** Scheduled runs may start a few minutes late; fine for a daily brief.
- **Workflow auto-disable:** Repos with no commits for 60 days disable scheduled workflows. Committing `garmin.db` each run prevents this.
- **Token expiry:** Re-run `scripts/mint_token.py` when Actions fail auth (~yearly).
- **Gemini privacy:** Free tier may use inputs for training. The digest contains only aggregated numbers — no names or emails.
- **Rate limits:** One Gemini call/day; flash → flash-lite fallback on 429.
- **NULL:** Missing Garmin fields are stored as NULL, never zero.
- **Gemini math:** All trends/comparisons are interpreted by the model from `daily_history` — verify numbers in the brief match the data if something looks off.
- **Gemini quota 0:** If you see `limit: 0` 429 errors, link a billing account on the GCP project tied to your API key (still $0 for one call/day within free tier).

## Project layout

```
src/
  config.py       # env, metrics registry, goals
  db.py           # SQLite
  garmin_client.py
  pull.py / backfill.py
  features.py     # format history for Gemini (no local stats)
  insight.py      # Gemini brief
  notify.py
  main.py
scripts/mint_token.py
.github/workflows/daily.yml
docs/sample-notification.png
```

## License

MIT — see [LICENSE](LICENSE).
