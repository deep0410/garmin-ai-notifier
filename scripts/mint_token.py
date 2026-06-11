#!/usr/bin/env python3
"""One-time Garmin Connect login: email + password + MFA → ~/.garminconnect tokens."""

from __future__ import annotations

import getpass
import logging
import os
import shutil
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

try:
    from dotenv import load_dotenv

    load_dotenv(_ROOT / ".env")
except ImportError:
    pass

from garminconnect import (
    Garmin,
    GarminConnectAuthenticationError,
    GarminConnectConnectionError,
    GarminConnectTooManyRequestsError,
)

# widget+cffi tokens are rejected by Garmin API (#369); mobile paths 429 easily.
# portal+cffi works — skip the rest so login goes straight there (~15–20s).
_DEFAULT_SKIP = frozenset({"widget+cffi", "mobile+cffi", "mobile+requests"})


def _skip_strategies() -> set[str]:
    raw = os.getenv("GARMIN_SKIP_STRATEGIES", "").strip()
    if raw:
        return {s.strip() for s in raw.split(",") if s.strip()}
    return set(_DEFAULT_SKIP)


def _configure(garmin: Garmin) -> None:
    garmin.client.skip_strategies = _skip_strategies()


def _clear_tokenstore(tokenstore_path: str) -> None:
    p = Path(tokenstore_path).expanduser()
    if p.is_dir():
        shutil.rmtree(p)
    elif p.is_file():
        p.unlink()
    p.mkdir(parents=True, exist_ok=True)


def _make_garmin(email: str, password: str) -> Garmin:
    garmin = Garmin(
        email=email,
        password=password,
        prompt_mfa=lambda: input("MFA code: ").strip(),
    )
    _configure(garmin)
    return garmin


def main() -> int:
    if os.getenv("DEBUG"):
        logging.basicConfig(level=logging.DEBUG)

    tokenstore = os.getenv("GARMINTOKENS", "~/.garminconnect")
    tokenstore_path = str(Path(tokenstore).expanduser())

    skip = _skip_strategies()
    if skip:
        print(f"Login skip_strategies: {sorted(skip)}")

    try:
        garmin = Garmin()
        _configure(garmin)
        garmin.login(tokenstore_path)
        print(f"Already logged in. Tokens at: {tokenstore_path}")
        return 0
    except (GarminConnectAuthenticationError, GarminConnectConnectionError) as err:
        print(f"No valid tokens — starting fresh login. ({err})")
        _clear_tokenstore(tokenstore_path)

    email_from_env = bool(os.getenv("EMAIL", "").strip())
    password_from_env = bool(os.getenv("PASSWORD", "").strip())
    if email_from_env:
        print("Using EMAIL from .env")

    while True:
        try:
            email = os.getenv("EMAIL", "").strip() or input("Email: ").strip()
            if password_from_env:
                password = os.environ["PASSWORD"]
            else:
                password = getpass.getpass("Password: ")
            _clear_tokenstore(tokenstore_path)
            garmin = _make_garmin(email, password)
            remaining = [
                s
                for s in (
                    "mobile+cffi",
                    "mobile+requests",
                    "widget+cffi",
                    "portal+cffi",
                    "portal+requests",
                )
                if s not in skip
            ]
            print(
                f"Logging in via {remaining[0] if remaining else 'portal'} "
                "(~15–20s, do not Ctrl+C)...",
                flush=True,
            )
            garmin.login(tokenstore_path)
            print(f"Login successful. Tokens saved to: {tokenstore_path}")
            return 0
        except GarminConnectTooManyRequestsError as err:
            print(f"Rate limit: {err}", file=sys.stderr)
            print("Wait 30–60 minutes before retrying login.", file=sys.stderr)
            return 1
        except GarminConnectAuthenticationError as err:
            print(f"Authentication failed: {err}", file=sys.stderr)
            if "social profile" in str(err).lower():
                print(
                    "Trying portal login path — clearing cached tokens. "
                    "If this repeats, set GARMIN_SKIP_STRATEGIES=widget+cffi,mobile+cffi,mobile+requests",
                    file=sys.stderr,
                )
                _clear_tokenstore(tokenstore_path)
            elif password_from_env:
                print("Check EMAIL/PASSWORD in .env (quotes, spaces, special chars).", file=sys.stderr)
            password_from_env = False
            continue
        except GarminConnectConnectionError as err:
            print(f"Connection error: {err}", file=sys.stderr)
            return 1
        except KeyboardInterrupt:
            print("\nCancelled.")
            return 130


if __name__ == "__main__":
    raise SystemExit(main())
