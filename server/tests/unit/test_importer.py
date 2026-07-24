import json
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
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


def test_parse_amount_strips_both_space_kinds():
    # a plain space and a non-breaking space (U+00A0) both used as thousands sep
    assert parse_amount_kop("1 500,00") == 150000
    assert parse_amount_kop("1 500,00") == 150000


def test_parse_amount_rounds_through_cents():
    # the double round() dodges float artifacts: 2.675 must land on 267, not 268
    assert parse_amount_kop("2,675") == 267


def test_parse_amount_blank_and_dash():
    assert parse_amount_kop("") is None
    assert parse_amount_kop("   ") is None
    assert parse_amount_kop("-") is None


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


def test_parse_statement_row_fields():
    rows, _ = parse_statement(SAMPLE_TSV)
    assert rows[0]["bank_category"] == "Переводы"
    assert rows[0]["mcc"] == ""
    assert rows[0]["description"] == "Сбербанк"
    assert rows[1]["bank_category"] == "Супермаркеты"
    assert rows[1]["mcc"] == "5411"
    # the hash is exactly sha256 of "date|amount|description"
    from app.importer import tx_hash

    assert rows[0]["hash"] == tx_hash("2026-07-03T19:48:24", -45000, "Сбербанк")


def test_parse_statement_semicolon_delimiter_and_quotes():
    line = '05.07.2026;05.07.2026;*1;OK;-20,00;RUB;-20,00;RUB;;Транспорт;4111;"Метро";0;0;-20,00\n'
    rows, errors = parse_statement(line)
    assert not errors
    assert len(rows) == 1
    # the surrounding double quotes must be stripped
    assert rows[0]["description"] == "Метро"
    assert rows[0]["amount"] == -2000


def test_parse_statement_accepts_exactly_twelve_columns():
    line = (
        "05.07.2026 10:00:00\t05.07.2026\t*1\tOK\t-10,00\tRUB\t-10,00\tRUB\t\t"
        "Кафе\t5812\tStarbucks\n"
    )
    rows, errors = parse_statement(line)
    assert not errors
    assert len(rows) == 1
    assert rows[0]["description"] == "Starbucks"
    assert rows[0]["mcc"] == "5812"


def test_parse_statement_too_few_columns_reports_count_and_line():
    rows, errors = parse_statement("a;b;c\n")
    assert not rows
    assert errors == [{"line": 1, "error": "expected >=12 columns, got 3", "raw": "a;b;c"}]


def test_parse_statement_error_line_numbers_are_one_based():
    # blank first line is skipped but still counted; the bad row is line 2
    nodate = "NODATE\t05.07.2026\t*1\tOK\t-10,00\tRUB\t-10,00\tRUB\t\tКафе\t5812\tX"
    rows, errors = parse_statement("\n" + nodate + "\n")
    assert not rows
    assert errors[0]["line"] == 2
    assert errors[0]["error"] == "unparseable date or amount"


def test_parse_statement_needs_both_date_and_amount():
    valid = "05.07.2026\t05.07.2026\t*1\tOK\t-10,00\tRUB\t-10,00\tRUB\t\tКафе\t5812\tX"
    bad_date = valid.replace("05.07.2026\t05.07.2026", "NODATE\t05.07.2026", 1)
    bad_amount = valid.replace("-10,00\tRUB\t-10,00", "-10,00\tRUB\tNOPE", 1)
    for line in (bad_date, bad_amount):
        rows, errors = parse_statement(line + "\n")
        assert not rows
        assert errors[0]["error"] == "unparseable date or amount"


def test_parse_statement_continues_after_every_kind_of_skip():
    valid = "05.07.2026 10:00:00\t05.07.2026\t*1\tOK\t-10,00\tRUB\t-10,00\tRUB\t\tКафе\t5812\tGOOD"
    failed = valid.replace("\tOK\t", "\tFAILED\t").replace("GOOD", "SKIP")
    bad_date = valid.replace("05.07.2026 10:00:00", "NODATE", 1).replace("GOOD", "BADDATE")
    text = "\n".join(["", "a;b", failed, bad_date, valid]) + "\n"
    rows, errors = parse_statement(text)
    # only the final valid row survives; a `break` instead of `continue` would drop it
    assert [r["description"] for r in rows] == ["GOOD"]
    # the too-few-columns line and the bad-date line each produce one error
    assert len(errors) == 2


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


def test_build_rules_skips_empty_bad_kind_and_null_keywords():
    groups = {1: "expense", 2: "income", 3: "other"}
    cats = [
        {"id": 1, "name": "NoKw", "keywords": "", "group_id": 1},  # empty → skipped
        {"id": 2, "name": "BadKind", "keywords": "x", "group_id": 3},  # not in/out → skipped
        {"id": 3, "name": "Groceries", "keywords": "Пят | Лента", "group_id": 1},
        {"id": 4, "name": "Salary", "keywords": "зарплата", "group_id": 2},
        {"id": 5, "name": "NullKw", "keywords": None, "group_id": 1},  # None → skipped
    ]
    rules = build_rules(cats, groups)
    # categories before Groceries are skipped with `continue`, not `break`
    assert [r["category_id"] for r in rules["OUT"]] == [3]
    assert [r["category_id"] for r in rules["IN"]] == [4]
    assert rules["OUT"][0]["name"] == "Groceries"
    # keywords are split on '|', trimmed and lowercased
    assert rules["OUT"][0]["keywords"] == ["пят", "лента"]


def test_categorize_guards_on_empty_desc_and_zero_amount():
    groups = {1: "expense", 2: "income"}
    cats = [
        {"id": 10, "name": "Cafe", "keywords": "кафе", "group_id": 1},
        {"id": 20, "name": "Salary", "keywords": "зарплата", "group_id": 2},
        {"id": 30, "name": "Decoy", "keywords": "xx", "group_id": 1},
    ]
    rules = build_rules(cats, groups)
    assert categorize("Кафе Пушкин", -500, rules) == 10
    assert categorize("Зарплата", 500, rules) == 20
    # a zero amount is never categorized, even with a matching description
    assert categorize("Кафе", 0, rules) is None
    # a tiny positive amount uses the income rules (sign split is strictly > 0)
    assert categorize("Зарплата", 1, rules) == 20
    # an empty description short-circuits to None (would match the "xx" decoy otherwise)
    assert categorize("", -500, rules) is None
    assert categorize(None, -500, rules) is None


def test_categorizer_agreement_with_sheet_history():
    """
    Port fidelity check: recategorize all historical transactions and compare
    with the sheet's own FIND_CATEGORIES output (auto_category column).
    """
    out = pathlib.Path(__file__).resolve().parents[3] / "migration" / "out"
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
