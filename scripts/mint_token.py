#!/usr/bin/env python3
"""One-time Garmin Connect login: email + password + MFA → ~/.garminconnect tokens."""

from __future__ import annotations

import getpass
import os
import sys
from pathlib import Path

from garminconnect import (
    Garmin,
    GarminConnectAuthenticationError,
    GarminConnectConnectionError,
    GarminConnectTooManyRequestsError,
)


def main() -> int:
    tokenstore = os.getenv("GARMINTOKENS", "~/.garminconnect")
    tokenstore_path = str(Path(tokenstore).expanduser())
    Path(tokenstore_path).mkdir(parents=True, exist_ok=True)

    try:
        garmin = Garmin()
        garmin.login(tokenstore_path)
        print(f"Already logged in. Tokens at: {tokenstore_path}")
        return 0
    except (GarminConnectAuthenticationError, GarminConnectConnectionError):
        print("No valid tokens — starting fresh login.")

    while True:
        try:
            email = os.getenv("EMAIL") or input("Email: ").strip()
            password = os.getenv("PASSWORD") or getpass.getpass("Password: ")
            garmin = Garmin(
                email=email,
                password=password,
                prompt_mfa=lambda: input("MFA code: ").strip(),
            )
            garmin.login(tokenstore_path)
            print(f"Login successful. Tokens saved to: {tokenstore_path}")
            return 0
        except GarminConnectTooManyRequestsError as err:
            print(f"Rate limit: {err}", file=sys.stderr)
            return 1
        except GarminConnectAuthenticationError:
            print("Wrong credentials — try again.")
            continue
        except GarminConnectConnectionError as err:
            print(f"Connection error: {err}", file=sys.stderr)
            return 1
        except KeyboardInterrupt:
            print("\nCancelled.")
            return 130


if __name__ == "__main__":
    raise SystemExit(main())
