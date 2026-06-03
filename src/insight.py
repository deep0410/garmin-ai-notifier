"""Gemini daily brief from formatted Garmin history."""

from __future__ import annotations

import json
import logging

from google import genai
from google.genai import errors as genai_errors

from src import config

logger = logging.getLogger(__name__)

PROMPT_TEMPLATE = """You are a sharp, no-nonsense performance coach reading one person's Garmin wellness data.

You receive JSON with:
- today: calendar date when this brief is generated (YYYY-MM-DD).
- reference_day: the date the daily brief is about (usually the day before today).
- goals: step target and sleep hour band.
- metrics_guide: what each metric means and good_direction ("up", "down", or "target" for sleep band).
- daily_history: every stored day, oldest to newest, with human-readable metric labels.

Your job: analyze the full history yourself — trends, highs/lows, vs goals, vs recent weeks.
Use ONLY numbers that appear in daily_history. Never invent values.
Respect good_direction (e.g. lower resting HR and stress are good; higher steps and HRV are good).

DIGEST:
{digest_json}

Write a phone notification brief. Rules:
- 60–100 words.
- Pick the 2–3 most meaningful signals for reference_day using the person's own history.
- No platitudes. At most one emoji if earned.

FORMAT — blank line between sections:

WATCH
• <concern: metric + number + why it matters vs their history>
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
