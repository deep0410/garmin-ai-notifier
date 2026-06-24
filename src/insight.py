"""Two-stage Gemini daily brief.

Stage 1 (Analyst): reads the deterministic feature report (already crunched from ~120
days by src.analysis) and decides WHAT matters -> structured JSON.
Stage 2 (Editor): turns those findings into the final phone notification -> text.

The heavy data work is done in code, so each LLM call sees a small, focused input.
"""

from __future__ import annotations

import json
import logging

from google import genai
from google.genai import errors as genai_errors

from src import config

logger = logging.getLogger(__name__)


# --- Stage 1: Analyst -------------------------------------------------------------
ANALYST_PROMPT = """You are a sports physiologist analyzing one person's Garmin (Venu 3) wellness data.

You are given a FEATURE REPORT already computed from up to ~120 days of history. You do NOT
see raw daily rows - the statistics are done for you. Each metric includes:
- value (current: last night for overnight metrics, most recent completed day for activity),
- unit, good_direction ("up"/"down"/"target" band/"status" text),
- avg_30d, pct_vs_30d, z (std-devs from baseline), percentile (0-100 within history),
- extreme ("highest/lowest in history"), signal ("good"/"watch"/"neutral"),
- today_partial when today's activity is still accruing.

Context fields: today, time_of_day, hour_local, reference_day, reference_day_is_today,
profile (age/sex/height/weight - calibrate norms to this person), goals, history_span,
no_data_metrics (absent on this device - ignore, never mention).

Rules:
- Use ONLY values in the report. Never invent numbers.
- Trust `signal` and `z`: |z|>=0.8 is a real deviation; small wobbles are noise, not news.
- reference_day_is_today=true means today's activity is PARTIAL: never treat low partial
  steps/floors as a failure; if early in the day, today's activity is "still ahead".
- Calibrate to profile (e.g. an HRV/resting-HR that's good for their age).
- Express standout values as natural time windows ("best in ~3 weeks"); NEVER "personal
  best", "all-time", "on record", or any day count.

FEATURE REPORT:
{report_json}

Return ONLY valid JSON (no prose, no code fences) with this shape:
{{
  "headline": "<one clause whole-body verdict, e.g. 'a green-light day' / 'recovered but under-slept' / 'ease off today'>",
  "domains": {{"recovery": "<one sentence with key numbers>", "sleep": "...", "activity": "...", "fitness": "..."}},
  "wins": ["<fact with number, from one domain>", "..."],
  "watches": ["<only genuine signal=='watch' deviations; [] if none>"],
  "today": ["<1-2 concrete actions, time-of-day aware>"],
  "fact": "<one physiology fact tied to a specific metric above>"
}}
Only include domains that have data. wins: up to 3, each a DIFFERENT domain. watches: 0-2, one per theme.
"""


# --- Stage 2: Editor --------------------------------------------------------------
EDITOR_PROMPT = """You are the editor writing the final morning phone notification from an analyst's findings.

It is currently {time_of_day} (hour {hour_local}). reference_day_is_today={ref_is_today}.

ANALYST FINDINGS (JSON):
{findings_json}

Write the notification EXACTLY in this layout, one blank line between sections:

OVERVIEW
<2-3 short flowing lines from "headline" plus the domain reads: a whole-body picture across
recovery, sleep, activity and fitness. Time-aware - today is still ahead. No bullets.>

WIN
- <from findings.wins - keep each to one tight line, different domains, no stacked sleep facts>

WATCH
- <from findings.watches - one per theme. If watches is empty, write exactly one line:
  "Nothing flagged - you're in good shape.">

TODAY
- <from findings.today - 1-2 concrete actions; don't nag about step/floor goals in the morning>

-
<findings.fact, trimmed to one short line>

Rules: ~90-140 words. Start bullet lines with a real bullet character under WIN, WATCH, TODAY
only (never under OVERVIEW). Short lines. Warm, direct, no platitudes. At most one emoji, only
if earned. Add no numbers not in the findings. Never mention day counts, "stored days",
"personal best", or "all-time".
"""


def _parse_findings(text: str) -> dict | str:
    """Best-effort JSON parse of the analyst output; fall back to raw text."""
    t = text.strip()
    if t.startswith("```"):
        t = t[3:]
        if t[:4].lower() == "json":
            t = t[4:]
        t = t.rsplit("```", 1)[0]
    start, end = t.find("{"), t.rfind("}")
    if start != -1 and end > start:
        try:
            return json.loads(t[start:end + 1])
        except json.JSONDecodeError:
            pass
    return text


def format_brief(text: str) -> str:
    lines = [ln.strip() for ln in text.strip().splitlines()]
    out: list[str] = []
    for ln in lines:
        if not ln:
            if out and out[-1] != "":
                out.append("")
            continue
        if out and out[-1] != "":
            prev = out[-1]
            if prev in ("WATCH", "WIN", "WINS", "TODAY") and not ln.startswith(("•", "-", "*")):
                out.append(f"• {ln}")
                continue
        # normalize leading "-"/"*" bullets to a real bullet
        if ln[:2] in ("- ", "* "):
            ln = "• " + ln[2:]
        out.append(ln)
    formatted = "\n".join(out).strip()
    while "\n\n\n" in formatted:
        formatted = formatted.replace("\n\n\n", "\n\n")
    return formatted


def _extract_text(response: object) -> str:
    text = getattr(response, "text", None)
    if text:
        return str(text).strip()
    candidates = getattr(response, "candidates", None) or []
    for cand in candidates:
        content = getattr(cand, "content", None)
        if not content:
            continue
        for part in getattr(content, "parts", None) or []:
            t = getattr(part, "text", None)
            if t:
                return str(t).strip()
    return ""


def _is_rate_limit(err: Exception) -> bool:
    if isinstance(err, genai_errors.ClientError):
        if getattr(err, "code", None) == 429:
            return True
    msg = str(err).lower()
    return "429" in msg or "rate" in msg or "quota" in msg or "resource_exhausted" in msg


def _complete(client: "genai.Client", prompt: str) -> str:
    """Run one prompt through the primary model, falling back on rate limit."""
    models = [config.GEMINI_MODEL, config.GEMINI_FALLBACK]
    last_err: Exception | None = None
    for i, model in enumerate(models):
        try:
            response = client.models.generate_content(model=model, contents=prompt)
            text = _extract_text(response)
            if not text:
                raise RuntimeError(f"Empty response from {model}")
            return text
        except Exception as err:
            last_err = err
            logger.warning("Gemini %s failed: %s", model, err)
            if i == 0 and _is_rate_limit(err):
                continue
            raise
    raise RuntimeError(f"Gemini failed: {last_err}") from last_err


def generate(report: dict) -> str:
    """Analyst -> Editor. `report` is the dict from src.analysis.build_feature_report."""
    if not config.GEMINI_API_KEY:
        raise ValueError("GEMINI_API_KEY is not set")

    client = genai.Client(api_key=config.GEMINI_API_KEY)

    analyst_raw = _complete(
        client,
        ANALYST_PROMPT.format(report_json=json.dumps(report, indent=2, default=str)),
    )
    findings = _parse_findings(analyst_raw)
    logger.info("Analyst findings parsed: %s", isinstance(findings, dict))

    findings_json = (
        json.dumps(findings, indent=2, default=str)
        if isinstance(findings, dict)
        else str(findings)
    )
    brief = _complete(
        client,
        EDITOR_PROMPT.format(
            findings_json=findings_json,
            time_of_day=report.get("time_of_day", "morning"),
            hour_local=report.get("hour_local", "?"),
            ref_is_today=report.get("reference_day_is_today", False),
        ),
    )
    return format_brief(brief)
