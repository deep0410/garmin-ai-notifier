# Garmin Daily Brief — Upgrade Plan

Goal: a glanceable daily notification that synthesizes a **whole-body overview** from
**all available Garmin metrics**, is **time-of-day aware**, and avoids padding/duplication.

---

## 1. Reality check — what we capture today

From the committed `garmin.db` snapshot (8 days). Of 19 tracked columns:

**Working (10):** steps, resting HR, sleep duration, deep sleep, REM, stress avg, HRV avg,
intensity minutes, active kcal, fitness age.

**Broken — column exists but always null (likely extractor bugs):**
- `sleep_score` (0/8) — code reads `sleepScoresOverall`; real path is `dailySleepDTO.sleepScores.overall.value`
- `body_battery_high` / `body_battery_low` (0/8) — Body Battery returns a time-series array; high/low must be derived from it, not from `bodyBatteryHighestValue`
- `training_readiness` (0/8) — may need `get_morning_training_readiness` instead of `get_training_readiness`

**Sparse / device-dependent:** `vo2_max` (1/8), `spo2_avg` (1/8), `weight_grams` & `body_fat_percent` (0/8 — need a smart scale).

> So "you only talk about sleep" is half prompt, half data: the recovery metrics that belong at the
> top of an overview (Body Battery, training readiness, HRV status) aren't in the DB at all.

---

## 2. Full fetchable catalog (validated)

`garminconnect` exposes 94 `get_*` endpoints. Wellness-relevant ones, by domain
(✅ have & working · ⚠️ have but broken/sparse · ➕ available, not yet pulled · 🔒 needs device/scale):

### Recovery & readiness
| Metric | Endpoint | Status |
|---|---|---|
| HRV overnight avg | `get_hrv_data` | ✅ |
| HRV **status** (vs personal baseline: balanced/low) | `get_hrv_data` | ➕ |
| Body Battery high/low + charged/drained | `get_body_battery` / `_events` | ⚠️ broken |
| Training readiness (0–100, 6-factor) | `get_morning_training_readiness` | ⚠️ broken |
| Recovery time (hrs) | `get_training_status` | ➕ |
| Resting HR | `get_rhr_day` | ✅ |
| Sleep score | `get_sleep_data` | ⚠️ broken |
| Respiration (avg/lowest, overnight) | `get_respiration_data` | ➕ |
| SpO2 (avg/lowest) | `get_spo2_data` | ⚠️ sparse |

### Sleep detail
| Total / Deep / REM | `get_sleep_data` | ✅ |
| Light, Awake, restless moments | `get_sleep_data` | ➕ |
| Sleep need (hrs) | `get_sleep_data` | ➕ 🔒 |
| Overnight HRV / respiration / SpO2 | `get_sleep_data` | ➕ |

### Activity & training load
| Steps / Intensity min / Active kcal | `get_stats` | ✅ |
| Floors climbed | `get_floors` | ➕ |
| Total / resting / BMR calories, distance | `get_stats` | ➕ |
| Acute load (7d), training status verdict | `get_training_status` | ➕ 🔒 |

### Fitness (slow-moving)
| VO2 max | `get_max_metrics` | ⚠️ sparse |
| Fitness age | `get_fitnessage_data` | ✅ |
| Endurance score | `get_endurance_score` | ➕ 🔒 |
| Hill score | `get_hill_score` | ➕ 🔒 |
| Race predictions (5k–marathon) | `get_race_predictions` | ➕ 🔒 |

### Body composition / other (situational)
| Weight, body fat, BMI, muscle | `get_body_composition` | 🔒 scale |
| Stress breakdown (rest/low/med/high min) | `get_all_day_stress` | ➕ |
| Hydration | `get_hydration_data` | ➕ |
| Blood pressure | `get_blood_pressure` | 🔒 |

**Step 0 (diagnostic):** before adding columns, run a script that calls every candidate endpoint for
one real day, dumps raw JSON, and reports which return data for *this* device. That separates true bugs
(Body Battery, sleep score) from genuine hardware gaps (training status, endurance score). We then add
only columns that actually populate.

---

## 3. New architecture — staged pipeline (2–3 LLM calls + deterministic stats)

Single-prompt summarization is why the brief grabs sleep and pads. Split the work:

**Stage A — Feature computation (code, no LLM).** For every populated metric: latest value,
7d & 30d mean, trend/delta, vs goal, percentile-in-history, a **significance flag**, and a
**data-present flag**. Deterministic → no hallucinated averages, no "stale" filler. Grouped by domain.
This also enforces *conservative triggering*: only significant deviations become candidate WATCH items.

**Stage B — Analyst (LLM call 1).** Input: the computed feature table + time-of-day. Output:
structured JSON — a verdict per domain, ranked notable facts, and candidate wins/watches/today-actions,
each tied to real numbers. Reasoning only, no formatting. Must score *every* domain that has data, so
nothing gets ignored.

**Stage C — Editor (LLM call 2).** Input: analyst JSON. Output: the final phone notification —
glanceable, word-limited, with the structure below. Separates *what to say* from *how to say it*,
which is what kills the duplication and padding.

**Stage D — QA/format (optional LLM call 3, or pure code).** Enforce word count, dedupe themes
(no two sleep facts in WATCH), verify no claims about null domains, confirm section structure.

Cost stays ~$0 (Gemini free tier; 2–3 calls/day).

---

## 4. New notification structure

```
OVERVIEW
<2–3 line whole-body verdict across recovery / sleep / activity / fitness, with a headline call>

WIN
• <point from one domain>
• <optional point from a DIFFERENT domain>

WATCH
• <only if a significance flag fired; one per theme>

TODAY
• <one concrete action, time-of-day aware — no step-goal nag in the morning>

—
<one physiology fact tied to a metric actually mentioned>
```

Rules: OVERVIEW is the synthesis (touches every domain with data); WIN/WATCH/TODAY carry the
drill-down detail and may hold multiple points **from different domains**; never stack same-theme facts;
never mention "stored days"/`day_count`; early in the day treat today's activity as "still ahead."

---

## 4b. Device reality — Garmin Venu 3 / 3S (validated)

Confirmed against the live diagnostic + Garmin's manual. The Venu 3 **does** support VO2 max
(running & cycling) and Pulse Ox — earlier "device gap" call was wrong for those.

- **Captured & working:** Body Battery, HRV + HRV status, sleep score/stages/respiration/sleep
  stress/awakenings, stress avg+peak, floors, steps, intensity, active kcal, resting HR, fitness age.
- **Supported but conditional (extractors already in place, populate when data exists):**
  - **VO2 max** — only updates after a qualifying outdoor brisk walk/run. Do one and it fills in.
  - **Pulse Ox / SpO2** — off by default (battery saver). Enable: watch → Settings → Pulse Ox →
    During Sleep / All Day.
- **Genuinely not on the Venu 3** (correctly excluded): Training Readiness, Training Status,
  Race Predictor, Endurance/Hill score.
- **Profile context added:** age, sex, height, weight now fetched (`get_userprofile_settings`) and
  passed to the brief so the coach calibrates to the person, not generic norms.

## 4c. Status — IMPLEMENTED

The staged pipeline is now live in code:

- `src/analysis.py` — deterministic feature engine. Caps history to the most recent
  `HISTORY_DAYS` (default **120**), computes per-metric value/avg_30d/trend/z/percentile/
  extreme/signal grouped by domain. Output ≈ **1,150 tokens** (was ~40k of raw rows).
- `src/insight.py` — **Stage 1 Analyst** (feature report → structured findings JSON) then
  **Stage 2 Editor** (findings → final notification). Each call sees a small input.
- `src/main.py` — `login → pull → fetch_profile → analysis.build_feature_report → insight.generate → notify`.
- Profile (age/sex/height/weight) flows in so norms are calibrated to the person.
- `HISTORY_DAYS` env var tunes the window without code changes.

## 5. Build order

1. **Diagnostic script** — dump raw JSON for all candidate endpoints (needs your Garmin tokens; you run it).
2. **Fix broken extractors** — sleep score, Body Battery, training readiness key paths.
3. **Add new columns + extractors** — for endpoints that returned real data (HRV status, respiration,
   training status/load, floors, stress breakdown, fitness scores…). DB auto-migrates.
4. **Backfill** to repopulate history with the new fields.
5. **Stage A feature module** (deterministic stats).
6. **Stage B/C prompts** (analyst → editor), optional Stage D.
7. **Dry-run** against real DB; iterate on a couple of sample briefs before going live.
