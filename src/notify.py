"""Push daily brief via ntfy."""

from __future__ import annotations

import os

import requests


def _require(name: str) -> str:
    val = os.getenv(name, "").strip()
    if not val:
        raise ValueError(f"Missing required env var: {name}")
    return val


def send(title: str, body: str) -> None:
    topic = _require("NTFY_TOPIC")
    url = f"https://ntfy.sh/{topic}"
    resp = requests.post(
        url,
        data=body.encode("utf-8"),
        headers={"Title": title},
        timeout=30,
    )
    resp.raise_for_status()
