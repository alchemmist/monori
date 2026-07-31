"""
Run the REAL TBankPlaywrightConnector against a prepared profile, headless,
exactly as prod does — to reproduce/confirm sync errors locally.

Feeds it the trusted-device profile captured by explore_tbank.py as its session
blob, so it should skip login (cookies still valid) and go straight to the
operations export. Prints each stage and any error.
"""

import base64
import io
import os
import sys
import tarfile
from typing import cast

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "server"))

from app.connectors.base import JsonObject, SmsRequired, SyncResult
from app.connectors.tbank_playwright import TBankPlaywrightConnector

PROFILE_DIR = os.environ.get("PROFILE_DIR", "/tmp/tbank-explore/profile")


def archive_profile(work_dir: str) -> str:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        tar.add(work_dir, arcname=".")
    return base64.b64encode(buf.getvalue()).decode()


def main() -> None:
    session: JsonObject = {"profile": archive_profile(PROFILE_DIR)}
    # phone/password only used if the trusted session lapsed; code is the
    # quick-login pin. Fill from env if you want to exercise a full re-login.
    creds: JsonObject = {
        "phone": os.environ.get("TBANK_PHONE", ""),
        "password": os.environ.get("TBANK_PASSWORD", ""),
        "code": os.environ.get("TBANK_CODE", ""),
    }
    print(f"profile blob: {len(cast('str', session['profile']))} b64 chars")
    print(f"headless: {TBankPlaywrightConnector._headless()}")

    conn = TBankPlaywrightConnector(creds, session)
    try:
        result: SyncResult = conn.sync()
    except SmsRequired as e:
        print(f"RESULT: SmsRequired -> {e} (trusted session lapsed, needs OTP)")
        conn.close()
        return
    except Exception as e:  # noqa: BLE001
        print(f"RESULT: ERROR -> {type(e).__name__}: {e}")
        return
    rows = result.rows
    print(f"RESULT: OK -> {len(rows)} rows parsed")
    if rows:
        ds = sorted(r["date"] for r in rows)
        print(f"  span {ds[0]} .. {ds[-1]}")
        print(f"  session updated: {'profile' in cast('JsonObject', result.session or {})}")


if __name__ == "__main__":
    main()
