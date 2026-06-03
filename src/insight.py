"""Gemini daily brief from precomputed digest."""

from __future__ import annotations

import json
import logging

from google import genai
from google.genai import errors as genai_errors

from src import config

logger = logging.getLogger(__name__)

PROMPT_TEMPLATE = """You are a sharp, no-nonsense performance coach reading one person's Garmin data.
You are given a precomputed statistical digest (all math is already done correctly —
do NOT recompute or invent numbers; only use what's provided).

DIGEST:
{digest_json}

Write a daily brief as a phone notification. Rules:
- 60–100 words, plain text, no markdown headers, at most one emoji and only if it earns its place.
- Do NOT list every metric. Choose the 2–3 MOST meaningful signals from top_signals and the
  digest, and explain why they matter using THIS person's own history (percentiles, trends,
  streaks, correlations) — e.g. "your resting HR hit a 90-day low, and it follows three nights
  back in your sleep target band."
- Respect good_direction: never frame a worsening metric as positive.
- Include exactly one concrete, specific action for today that follows from the data.
- End with one short, genuinely interesting physiology/training fact tied to a metric you mentioned.
- Be specific and human. No platitudes, no "keep it up!", no generic wellness filler.
"""


def build_prompt(digest: dict) -> str:
    return PROMPT_TEMPLATE.format(
        digest_json=json.dumps(digest, indent=2, default=str)
    )


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
            return text
        except Exception as err:
            last_err = err
            logger.warning("Gemini %s failed: %s", model, err)
            if i == 0 and _is_rate_limit(err):
                continue
            raise

    raise RuntimeError(f"Gemini failed: {last_err}") from last_err
