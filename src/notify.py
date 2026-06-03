"""Pluggable notification: ntfy | telegram | email."""

from __future__ import annotations

import os
import smtplib
from email.mime.text import MIMEText

import requests

from src import config


def _require(name: str) -> str:
    val = os.getenv(name, "").strip()
    if not val:
        raise ValueError(f"Missing required env var for {config.NOTIFIER}: {name}")
    return val


def _send_ntfy(title: str, body: str) -> None:
    topic = _require("NTFY_TOPIC")
    url = f"https://ntfy.sh/{topic}"
    resp = requests.post(
        url,
        data=body.encode("utf-8"),
        headers={"Title": title},
        timeout=30,
    )
    resp.raise_for_status()


def _send_telegram(title: str, body: str) -> None:
    token = _require("TELEGRAM_BOT_TOKEN")
    chat_id = _require("TELEGRAM_CHAT_ID")
    text = f"*{title}*\n\n{body}"
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    resp = requests.post(
        url,
        json={"chat_id": chat_id, "text": text, "parse_mode": "Markdown"},
        timeout=30,
    )
    resp.raise_for_status()


def _send_email(title: str, body: str) -> None:
    user = _require("EMAIL_USER")
    password = _require("EMAIL_APP_PASSWORD")
    to_addr = _require("EMAIL_TO")
    msg = MIMEText(body)
    msg["Subject"] = title
    msg["From"] = user
    msg["To"] = to_addr
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=30) as smtp:
        smtp.login(user, password)
        smtp.sendmail(user, [to_addr], msg.as_string())


def send(title: str, body: str) -> None:
    notifier = config.NOTIFIER
    if notifier == "ntfy":
        _send_ntfy(title, body)
    elif notifier == "telegram":
        _send_telegram(title, body)
    elif notifier == "email":
        _send_email(title, body)
    else:
        raise ValueError(f"Unknown NOTIFIER: {notifier} (use ntfy, telegram, or email)")
