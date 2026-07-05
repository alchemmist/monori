"""Export all budget data from Google Sheets to JSON files in migration/raw/.

Dumps, per sheet, both unformatted values and formulas so downstream steps can
tell hand-entered budget numbers from formula-derived ones.
"""

import json
import pathlib

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

SPREADSHEET_ID = "1w9ue66Dgc4Ut8xA4kzhaUzeerYaXDvYTj6sRqIBCpM0"
TOKEN_PATH = pathlib.Path.home() / ".stefania/gsheets/token.json"
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
