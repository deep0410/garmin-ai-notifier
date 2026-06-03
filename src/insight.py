"""Gemini daily brief from precomputed digest."""

from __future__ import annotations

import json
import logging

from google import genai
from google.genai import errors as genai_errors

from src import config

logger = logging.getLogger(__name__)

PROMPT_TEMPLATE = """You are a sharp, no-nonsense performance coach reading one person's Garmin data.

You receive a JSON digest with these sections:
- metrics: precomputed history stats (percentiles, z-scores, trends, streaks, records). Do NOT recalculate these.
- pass_through: metrics WITHOUT precomputed stats — use reference_day and last_7d only; each has label, unit, good_direction, hint.
- yesterday_snapshot: all reference-day values (human-readable labels).
- last_7d: last 7 calendar days of compact daily values for context.
- top_signals: ranked highlights — start here if non-empty.
- correlations: cross-metric patterns.

Reference day is digest.as_of. Respect good_direction everywhere (e.g. lower resting HR and stress are good; higher is bad unless good_direction is up).

DIGEST:
{digest_json}

Write a phone notification brief. Rules:
- 60–100 words. Use ONLY numbers from the digest; never invent values.
- Pick 2–3 meaningful points (mix metrics stats, pass_through trends, and last_7d if useful).
- You may cite pass_through metrics (deep sleep, REM, Body Battery low, active kcal, weight) when relevant.
- No platitudes. At most one emoji if earned.

FORMAT — blank line between sections:

WATCH
• <concern: metric + number + vs history or 7d context>
• <optional second concern>

WINS
• <bright spot>
• <optional second win>

TODAY
<one concrete imperative for today>

—
<one short physiology/training fact tied to a metric you mentioned>

Use "•" only under WATCH and WINS. Short lines. No single paragraph.
"""


def build_prompt(digest: dict) -> str:
    return PROMPT_TEMPLATE.format(
        digest_json=json.dumps(digest, indent=2, default=str)
    )


def format_brief(text: str) -> str:
    """Normalize spacing so ntfy/Telegram show clear sections."""
    lines = [ln.strip() for ln in text.strip().splitlines()]
    out: list[str] = []
    for ln in lines:
        if not ln:
            if out and out[-1] != "":
                out.append("")
            continue
        if out and out[-1] != "":
            prev = out[-1]
            if prev in ("WATCH", "WINS") and not ln.startswith("•"):
                out.append(f"• {ln}")
                continue
            if prev == "—" or ln == "—":
                out.append(ln)
                continue
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
        parts = getattr(content, "parts", None) or []
        for part in parts:
            t = getattr(part, "text", None)
            if t:
                return str(t).strip()
    return ""


def _is_rate_limit(err: Exception) -> bool:
    if isinstance(err, genai_errors.ClientError):
        code = getattr(err, "code", None)
        if code == 429:
            return True
    msg = str(err).lower()
    return "429" in msg or "rate" in msg or "quota" in msg or "resource_exhausted" in msg


def generate(digest: dict) -> str:
    if not config.GEMINI_API_KEY:
        raise ValueError("GEMINI_API_KEY is not set")

    client = genai.Client(api_key=config.GEMINI_API_KEY)
    prompt = build_prompt(digest)
    models = [config.GEMINI_MODEL, config.GEMINI_FALLBACK]

    last_err: Exception | None = None
    for i, model in enumerate(models):
        try:
            response = client.models.generate_content(model=model, contents=prompt)
            text = _extract_text(response)
            if not text:
                raise RuntimeError(f"Empty response from {model}")
            return format_brief(text)
        except Exception as err:
            last_err = err
            logger.warning("Gemini %s failed: %s", model, err)
            if i == 0 and _is_rate_limit(err):
                continue
            raise

    raise RuntimeError(f"Gemini failed: {last_err}") from last_err
