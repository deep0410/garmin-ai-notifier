# Garmin Daily AI Insights

**Free daily AI brief on your Garmin data — Gemini reads your full history, push to your phone. ~$0.40/mo AWS for token storage; everything else $0.**

Fully automated pipeline: pull Garmin Connect into SQLite, send formatted daily history to Gemini for analysis, and deliver a short coached brief via ntfy. The job runs on GitHub Actions when triggered; **daily timing uses a free external cron** ([crontab.guru](https://crontab.guru/) + [cron-job.org](https://cron-job.org/en/)), not GitHub’s built-in schedule (unreliable).

Garmin auth tokens live in **AWS Secrets Manager** (not in this repo). CI restores them before each run and writes back rotated tokens automatically.

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

**Cost:** ~$0.40/month (AWS Secrets Manager for Garmin tokens) + $0 (Garmin API, Gemini free tier, GitHub Actions, ntfy).

## Prerequisites

| Requirement | Why |
| ----------- | --- |
| **AWS account** | CI stores Garmin tokens in Secrets Manager ([create an account](https://aws.amazon.com/free/) if needed) |
| **AWS CLI v2** | One-time infra bootstrap and token seeding |
| **IAM permissions** | Your AWS user must create OIDC provider, IAM role/policy, and a secret (admin during setup is fine) |
| **Garmin Connect** | Email + password + MFA (once, at local mint) |
| **GitHub repo** | For Actions and `garmin.db` |

CI uses **GitHub OIDC** to assume an IAM role — no long-lived AWS access keys in GitHub.

## Setup

### 1. Python environment

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Mint Garmin token (local, MFA once)

```bash
cp .env.example .env   # fill EMAIL and PASSWORD
python scripts/mint_token.py
```

Use your Garmin email, password, and MFA code. Tokens are saved to `~/.garminconnect`.

`garminconnect` 0.3.x uses short-lived access tokens and a **rotating refresh token**. Daily CI runs self-heal by persisting refreshed tokens to AWS (see step 5). Re-mint locally only if the pipeline is idle 30+ days or Garmin revokes your session.

### 3. Backfill history

```bash
BACKFILL_DAYS=180 python -m src.backfill
```

Creates `garmin.db`. Commit it to your repo after backfill completes (re-run backfill after schema changes to refresh columns).

### 4. AWS setup (one-time)

Install [AWS CLI v2](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html) and configure credentials (`aws sts get-caller-identity` should work).

```bash
bash scripts/aws_bootstrap.sh
```

This creates (via AWS CLI): GitHub OIDC provider, Secrets Manager secret, IAM role/policy. It prints `ROLE_ARN` — save it.

Set the GitHub repository secret:

```bash
gh secret set AWS_ROLE_ARN --body "arn:aws:iam::ACCOUNT:role/garmin-ai-notifier-github-actions"
```

### 5. Seed tokens to AWS

After `mint_token.py`, upload local tokens to Secrets Manager:

```bash
# AWS_REGION and GARMIN_TOKEN_SECRET_NAME are in .env.example
bash scripts/seed_aws_secret.sh

# Verify round-trip
bash scripts/token_aws.sh restore
test -f ~/.garminconnect/garmin_tokens.json && echo OK
```

### 6. GitHub Actions secrets

| Secret | Where | Purpose |
| ------ | ----- | ------- |
| `AWS_ROLE_ARN` | GitHub only | IAM role for OIDC (from `aws_bootstrap.sh`) |
| `GEMINI_API_KEY` | GitHub + `.env` | [Google AI Studio](https://aistudio.google.com) |
| `NTFY_TOPIC` | GitHub + `.env` | Long random ntfy topic |

**Not stored in git:** Garmin email/password, MFA codes, `garmin_tokens.json`, AWS access keys.

**In AWS Secrets Manager:** base64 tar of `~/.garminconnect` (CI updates this after every run).

### 7. ntfy

Install the [ntfy app](https://ntfy.sh), subscribe to a long random topic, set `NTFY_TOPIC` in `.env` and GitHub secrets.

### 8. Test locally

```bash
cp .env.example .env   # Gemini + ntfy; Garmin tokens already in ~/.garminconnect
python -m src.main
```

Local runs use `~/.garminconnect` directly — no AWS needed for day-to-day local testing.

### 9. Deploy

Create a GitHub repo, commit everything including `garmin.db`, add secrets from step 6, run **Actions → garmin-daily → Run workflow** once to verify CI and the AWS token round-trip. The repo can be **public** if you accept that `garmin.db` exposes daily health numbers (see below).

### 10. Daily schedule (crontab.guru + cron-job.org)

**Do not use GitHub Actions `on.schedule`.** Scheduled workflows on GitHub are often delayed, skipped, or never registered after cron edits. Use a free external cron instead.

1. **Pick a time** — e.g. 1:05 PM Eastern. Open [crontab.guru](https://crontab.guru/) and build a standard 5-field cron for your runner’s timezone.  
   - Example for **1:05 PM in `America/New_York` on the cron host**: many users use UTC on [cron-job.org](https://cron-job.org/en/) → `5 17 * * *` (17:05 UTC ≈ 1:05 PM EDT; adjust in winter or when DST changes). crontab.guru shows what each field means as you edit.

2. **Create a GitHub PAT** (fine-grained or classic) with **`actions:write`** and **`contents: read`** on this repo. Copy it once; you will paste it into cron-job.org, not into GitHub secrets.

3. **Create a cron job** at [cron-job.org](https://cron-job.org/en/) (free account):
   - **URL:** `https://api.github.com/repos/YOUR_USER/YOUR_REPO/actions/workflows/daily.yml/dispatches`
   - **Method:** `POST`
   - **Schedule:** the expression from step 1 (cron-job.org has a UI; cross-check on crontab.guru)
   - **Headers:**
     - `Accept: application/vnd.github+json`
     - `Authorization: Bearer YOUR_GITHUB_PAT`
     - `Content-Type: application/json`
   - **Body:** `{"ref":"main"}`

4. **Test:** Run the job once from cron-job.org; confirm a **workflow_dispatch** run appears under Actions and you get the ntfy brief.

**Alternative — run on your Mac (no Actions):** use the same expression in local `crontab -e` (built with crontab.guru):

```bash
5 13 * * * cd /path/to/garmin && .venv/bin/python -m src.main >> /tmp/garmin-cron.log 2>&1
```

Set `TZ=America/New_York` in the crontab line or in your shell profile if you want local Eastern time. You must commit `garmin.db` yourself if you want it in the repo.

## How CI auth works

1. GitHub OIDC → assume `AWS_ROLE_ARN`
2. `scripts/token_aws.sh restore` from Secrets Manager → `~/.garminconnect`
3. `python -m src.main` (garminconnect may rotate tokens on disk)
4. `scripts/token_aws.sh persist` back to Secrets Manager (runs even if Gemini/ntfy fails)
5. Commit `garmin.db` only on success

## Migrating from GARMIN_TOKENS_B64

If you previously used the static GitHub secret:

1. `bash scripts/aws_bootstrap.sh`
2. `python scripts/mint_token.py` (or reuse valid `~/.garminconnect`)
3. `bash scripts/seed_aws_secret.sh`
4. Set `AWS_ROLE_ARN`; delete `GARMIN_TOKENS_B64` from GitHub secrets
5. Run the workflow twice to confirm rotation write-back

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

When triggered via cron-job.org, GitHub Actions runs the same command, persists rotated tokens to AWS, commits updated `garmin.db`, and pushes.

## Gotchas

- **AWS account required for CI** — Garmin tokens are not stored in GitHub secrets anymore.
- **Do not delete the AWS secret** while CI is active.
- **Token self-healing:** daily runs persist rotated refresh tokens to AWS; re-mint + re-seed only if idle 30+ days or auth is revoked.
- **MFA:** only at `mint_token.py` bootstrap (SMS cannot be automated).
- **`aws_bootstrap.sh`** is idempotent for infra; a broken token store is fixed with `seed_aws_secret.sh`, not re-bootstrap.
- **GitHub `on.schedule`:** Intentionally not used — use [crontab.guru](https://crontab.guru/) + [cron-job.org](https://cron-job.org/en/) instead (see §10).
- **cron-job.org 4xx:** PAT needs `actions:write`; URL must match `daily.yml` on `main`; body must be `{"ref":"main"}`.
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
scripts/
  mint_token.py
  token_aws.sh       # pack | restore | persist
  seed_aws_secret.sh # one-time upload after mint
  aws_bootstrap.sh   # AWS CLI infra setup
.github/workflows/daily.yml
docs/sample-notification.png
```

## License

MIT — see [LICENSE](LICENSE).
