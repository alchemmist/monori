"""Export all budget data from a Google Sheets budget to JSON in migration/raw/.

Dumps, per sheet, both unformatted values and formulas so downstream steps can
tell hand-entered budget numbers from formula-derived ones.

This targets the layout of the monori budget spreadsheet template (Transactions,
Categories and one sheet per year). To migrate your own copy, set the sheet id
and an OAuth token path:

    export MONORI_SHEET_ID=<your spreadsheet id from its URL>
    export MONORI_GSHEETS_TOKEN=~/.config/monori/gsheets-token.json
    python migration/export_sheets.py

The spreadsheet id can also be passed as the first argument.
"""

import json
import os
import pathlib
import sys

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

SPREADSHEET_ID = os.environ.get("MONORI_SHEET_ID") or (sys.argv[1] if len(sys.argv) > 1 else "")
TOKEN_PATH = pathlib.Path(
    os.environ.get("MONORI_GSHEETS_TOKEN", "~/.config/monori/gsheets-token.json")
).expanduser()
OUT_DIR = pathlib.Path(__file__).parent / "raw"

YEAR_SHEETS = [str(y) for y in range(2020, 2028)]


def fetch(svc, rng, render):
    return (
        svc.spreadsheets()
        .values()
        .get(
            spreadsheetId=SPREADSHEET_ID,
            range=rng,
            valueRenderOption=render,
            dateTimeRenderOption="SERIAL_NUMBER",
        )
        .execute()
        .get("values", [])
    )


def main():
    if not SPREADSHEET_ID:
        sys.exit("set MONORI_SHEET_ID (or pass the spreadsheet id as the first argument)")
    if not TOKEN_PATH.exists():
        sys.exit(f"OAuth token not found at {TOKEN_PATH}; set MONORI_GSHEETS_TOKEN")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    creds = Credentials.from_authorized_user_file(str(TOKEN_PATH))
    svc = build("sheets", "v4", credentials=creds)

    dumps = {
        "transactions": ("Transactions!A1:V7000", ["UNFORMATTED_VALUE"]),
        "categories": ("Categories!A1:H41", ["UNFORMATTED_VALUE", "FORMULA"]),
    }
    for year in YEAR_SHEETS:
        dumps[f"year_{year}"] = (f"'{year}'!A1:BB121", ["UNFORMATTED_VALUE", "FORMULA"])

    for name, (rng, renders) in dumps.items():
        payload = {}
        for render in renders:
            payload[render.lower()] = fetch(svc, rng, render)
        out = OUT_DIR / f"{name}.json"
        out.write_text(json.dumps(payload, ensure_ascii=False))
        rows = len(payload[renders[0].lower()])
        print(f"{name}: {rows} rows -> {out.name}")


if __name__ == "__main__":
    main()
