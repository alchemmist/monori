import json
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from app.importer import build_rules, categorize, parse_amount_kop, parse_date, parse_statement

SAMPLE_TSV = (
    "03.07.2026 19:48:24\t03.07.2026\t*2947\tOK\t-450,00\tRUB\t-450,00\tRUB\t\t"
    "Переводы\t\tСбербанк\t0\t0\t-450,00\n"
    "01.07.2026 12:00:00\t01.07.2026\t*2947\tOK\t-1 500,50\tRUB\t-1 500,50\tRUB\t\t"
    "Супермаркеты\t5411\tПятёрочка\t0\t0\t-1500,50\n"
    "01.07.2026\t01.07.2026\t*2947\tFAILED\t-100,00\tRUB\t-100,00\tRUB\t\t"
    "Супермаркеты\t5411\tЛента\t0\t0\t-100,00\n"
)


def test_parse_date():
    assert parse_date("03.07.2026 19:48:24").isoformat() == "2026-07-03T19:48:24"
    assert parse_date("03.07.2026").isoformat() == "2026-07-03T00:00:00"
    assert parse_date("2026-07-03") is None


def test_parse_amount():
    assert parse_amount_kop("-1 500,50") == -150050
    assert parse_amount_kop("500") == 50000
    assert parse_amount_kop("0,10") == 10
    assert parse_amount_kop("abc") is None


def test_parse_statement():
    rows, errors = parse_statement(SAMPLE_TSV)
    assert len(rows) == 2  # FAILED row skipped
    assert not errors
    assert rows[0]["date"] == "2026-07-03T19:48:24"
    assert rows[0]["amount"] == -45000
    assert rows[1]["description"] == "Пятёрочка"
    assert rows[1]["amount"] == -150050


def test_parse_statement_bad_line():
    rows, errors = parse_statement("garbage line\n")
    assert not rows
    assert len(errors) == 1


def test_categorize_first_rule_wins_and_sign_split():
    groups = {1: "expense", 2: "income"}
    cats = [
        {"id": 10, "name": "Groceries", "keywords": "Пятёрочка|Лента", "group_id": 1},
        {"id": 11, "name": "Entertainment", "keywords": "Лента", "group_id": 1},
        {"id": 20, "name": "Cashback", "keywords": "Кэшбэк", "group_id": 2},
    ]
    rules = build_rules(cats, groups)
    assert categorize("Пятёрочка", -100, rules) == 10
    assert categorize("ЛЕНТА", -100, rules) == 10  # first rule in order wins
    assert categorize("Зачисление кэшбэка", 100, rules) == 20
    assert categorize("Кэшбэк", -100, rules) is None  # wrong sign for income rule
    assert categorize("", -100, rules) is None


def test_categorizer_agreement_with_sheet_history():
    """Port fidelity check: recategorize all historical transactions and compare
    with the sheet's own FIND_CATEGORIES output (auto_category column)."""
    out = pathlib.Path(__file__).resolve().parent.parent.parent / "migration" / "out"
    if not (out / "transactions.json").exists():
        pytest.skip("migration/out fixtures not present (private Google Sheet data)")
    txs = json.loads((out / "transactions.json").read_text())
    cats_raw = json.loads((out / "categories.json").read_text())
    groups = {}
    group_ids = {}
    for i, g in enumerate(cats_raw["groups"], 1):
        group_ids[g["name"]] = i
        groups[i] = "income" if g["type"] == "IN" else "expense"
    cats = [
        {"id": i, "name": c["name"], "keywords": c["keywords"], "group_id": group_ids[c["group"]]}
        for i, c in enumerate(cats_raw["categories"], 1)
    ]
    name_by_id = {c["id"]: c["name"] for c in cats}
    rules = build_rules(cats, groups)

    # Known stale cell in the sheet: a +150 RUB refund ("Яндекс Расписания",
    # 2025-05-31) shows auto-category "Transport", but the current
    # FIND_CATEGORIES splits rules by amount sign, so a positive amount can
    # never match the expense rule. The sheet value is a frozen leftover; the
    # port's answer (uncategorized) is what the algorithm actually returns.
    known_stale = {("2025-05-31T23:18:27", "Яндекс Расписания")}

    mismatches = []
    for t in txs:
        if (t["date"], t["description"]) in known_stale:
            continue
        got_id = categorize(t["description"], round(t["amount"] * 100), rules)
        got = name_by_id.get(got_id, "")
        expected = t["auto_category"] or ""
        if got != expected:
            mismatches.append((t["date"], t["description"][:40], expected, got))
    assert mismatches == [], f"{len(mismatches)} disagreements, first: {mismatches[:5]}"
