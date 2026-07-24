"""
Bank statement parsing and auto-categorization.

The paste format is the bank's statement export: one transaction per line,
tab- or semicolon-separated, dates as dd.mm.yyyy [hh:mm:ss], decimal commas.
Categorization is a faithful port of the sheet's FIND_CATEGORIES: rules are
split into IN/OUT by category-group kind, the transaction sign picks the rule
set, and the first category (in definition order) whose keyword is a
case-insensitive substring of the description wins.
"""

import hashlib
import re
from datetime import datetime

COLUMNS = [
    "op_date",
    "pay_date",
    "card",
    "status",
    "op_amount",
    "op_currency",
    "amount",
    "currency",
    "cashback",
    "bank_category",
    "mcc",
    "description",
    "bonuses",
    "rounding",
    "rounded_total",
]

DATE_RE = re.compile(r"^(\d{2})\.(\d{2})\.(\d{4})(?:\s+(\d{2}):(\d{2})(?::(\d{2}))?)?$")


def parse_date(raw):
    m = DATE_RE.match(raw.strip())
    if not m:
        return None
    d, mo, y, hh, mm, ss = m.groups()
    return datetime(int(y), int(mo), int(d), int(hh or 0), int(mm or 0), int(ss or 0))


def parse_amount_kop(raw):
    """
    '-1 500,00' -> -150000 kopecks.
    """
    s = str(raw).strip().replace(" ", "").replace(" ", "").replace(",", ".")
    if not s or s in ("-", "."):
        return None
    try:
        # round through cents to dodge float artifacts
        return round(round(float(s), 2) * 100)
    except ValueError:
        return None


def tx_hash(date_iso, amount_kop, description):
    return hashlib.sha256(f"{date_iso}|{amount_kop}|{description}".encode()).hexdigest()


def parse_statement(text):
    """
    Returns (rows, errors). Each row: dict with date (ISO), amount (kopecks),
    description, bank_category, mcc, hash.
    """
    rows, errors = [], []
    for ln, line in enumerate(text.splitlines(), 1):
        if not line.strip():
            continue
        delim = "\t" if "\t" in line else ";"
        parts = [p.strip().strip('"') for p in line.split(delim)]
        if len(parts) < 12:
            errors.append(
                {"line": ln, "error": f"expected >=12 columns, got {len(parts)}", "raw": line[:200]}
            )
            continue
        rec = dict(zip(COLUMNS, parts + [""] * (len(COLUMNS) - len(parts)), strict=False))
        date = parse_date(rec["op_date"])
        amount = parse_amount_kop(rec["amount"])
        if date is None or amount is None:
            errors.append({"line": ln, "error": "unparseable date or amount", "raw": line[:200]})
            continue
        if rec["status"] and rec["status"].upper() == "FAILED":
            continue
        date_iso = date.strftime("%Y-%m-%dT%H:%M:%S")
        rows.append(
            {
                "date": date_iso,
                "amount": amount,
                "description": rec["description"],
                "bank_category": rec["bank_category"],
                "mcc": rec["mcc"],
                "hash": tx_hash(date_iso, amount, rec["description"]),
            }
        )
    return rows, errors


def build_rules(categories, groups):
    """
    categories: iterable of dicts with name/keywords/group_id;
    groups: id -> kind ('income'|'expense'). Returns {'IN': [...], 'OUT': [...]}.
    """
    rules: dict[str, list] = {"IN": [], "OUT": []}
    for c in categories:
        keywords = [k.strip().lower() for k in str(c["keywords"] or "").split("|") if k.strip()]
        if not keywords:
            continue
        kind = groups.get(c["group_id"])
        if kind not in ("income", "expense"):
            continue
        rules["IN" if kind == "income" else "OUT"].append(
            {"category_id": c["id"], "name": c["name"], "keywords": keywords}
        )
    return rules


def categorize(description, amount_kop, rules):
    """
    Returns category_id or None.
    """
    desc = str(description or "").lower()
    if not desc or amount_kop == 0:
        return None
    for rule in rules["IN" if amount_kop > 0 else "OUT"]:
        for kw in rule["keywords"]:
            if kw in desc:
                return rule["category_id"]
    return None
