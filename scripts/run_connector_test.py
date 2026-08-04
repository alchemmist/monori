"""Run the REAL TBankPlaywrightConnector against a prepared profile, headless.

Run it exactly as prod does to reproduce/confirm sync errors locally.

Feeds it the trusted-device profile captured by explore_tbank.py as its session
blob, so it should skip login (cookies still valid) and go straight to the
operations export. Prints each stage and any error.
"""

import base64
import io
import logging
import os
import sys
import tarfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "server"))

from app.connectors.base import JsonObject, SmsRequiredError, SyncResult
from app.connectors.tbank_playwright import TBankPlaywrightConnector

PROFILE_DIR = os.environ.get("PROFILE_DIR", "/tmp/tbank-explore/profile")
logger = logging.getLogger(__name__)


def archive_profile(work_dir: str) -> str:
    """Archive profile for this module."""
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        tar.add(work_dir, arcname=".")
    return base64.b64encode(buf.getvalue()).decode()


def main() -> None:
    """Run this module as a CLI entrypoint and return its exit code."""
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    session: JsonObject = {"profile": archive_profile(PROFILE_DIR)}
    # phone/password only used if the trusted session lapsed; code is the
    # quick-login pin. Fill from env if you want to exercise a full re-login.
    creds: JsonObject = {
        "phone": os.environ.get("TBANK_PHONE", ""),
        "password": os.environ.get("TBANK_PASSWORD", ""),
        "code": os.environ.get("TBANK_CODE", ""),
    }
    profile = session["profile"]
    if not isinstance(profile, str):
        message = "profile archive is not a string"
        raise TypeError(message)
    logger.info("profile blob: %s b64 chars", len(profile))
    logger.info("headless: %s", TBankPlaywrightConnector.headless())

    conn = TBankPlaywrightConnector(creds, session)
    try:
        result: SyncResult = conn.sync()
    except SmsRequiredError as e:
        logger.info("RESULT: SmsRequired -> %s (trusted session lapsed, needs OTP)", e)
        conn.close()
        return
    except Exception as e:  
        logger.error("RESULT: ERROR -> %s: %s", type(e).__name__, e)
        return
    rows = result.rows
    logger.info("RESULT: OK -> %s rows parsed", len(rows))
    if rows:
        ds = sorted(row.date for row in rows)
        logger.info("  span %s .. %s", ds[0], ds[-1])
        logger.info("  session updated: %s", "profile" in (result.session or {}))


if __name__ == "__main__":
    main()
