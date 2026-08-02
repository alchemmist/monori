import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
from app.importer import (
    CategoryDefinition,
    build_rules,
    categorize,
    parse_amount_kop,
    parse_date,
    parse_statement,
    tx_hash,
)

SAMPLE_TSV = (
    "03.07.2026 19:48:24\t03.07.2026\t*2947\tOK\t-450,00\tRUB\t-450,00\tRUB\t\t"
    "Transfers\t\tSberbank\t0\t0\t-450,00\n"
    "01.07.2026 12:00:00\t01.07.2026\t*2947\tOK\t-1 500,50\tRUB\t-1 500,50\tRUB\t\t"
    "Supermarkets\t5411\tPyaterochka\t0\t0\t-1500,50\n"
    "01.07.2026\t01.07.2026\t*2947\tFAILED\t-100,00\tRUB\t-100,00\tRUB\t\t"
    "Supermarkets\t5411\tLenta\t0\t0\t-100,00\n"
)


def test_parse_date() -> None:
    with_time = parse_date("03.07.2026 19:48:24")
    without_time = parse_date("03.07.2026")
    assert with_time is not None
    assert without_time is not None
    assert with_time.isoformat() == "2026-07-03T19:48:24+00:00"
    assert without_time.isoformat() == "2026-07-03T00:00:00+00:00"
    assert parse_date("2026-07-03") is None


def test_parse_amount() -> None:
    assert parse_amount_kop("-1 500,50") == -150050
    assert parse_amount_kop("500") == 50000
    assert parse_amount_kop("0,10") == 10
    assert parse_amount_kop("abc") is None


def test_parse_amount_strips_both_space_kinds() -> None:

    assert parse_amount_kop("1 500,00") == 150000
    assert parse_amount_kop("1\u00a0500,00") == 150000


def test_parse_amount_rounds_through_cents() -> None:

    assert parse_amount_kop("2,675") == 267


def test_parse_amount_blank_and_dash() -> None:
    assert parse_amount_kop("") is None
    assert parse_amount_kop("   ") is None
    assert parse_amount_kop("-") is None


def test_parse_statement() -> None:
    rows, errors = parse_statement(SAMPLE_TSV)
    assert len(rows) == 2
    assert not errors
    assert rows[0]["date"] == "2026-07-03T19:48:24"
    assert rows[0]["amount"] == -45000
    assert rows[1]["description"] == "Pyaterochka"
    assert rows[1]["amount"] == -150050


def test_parse_statement_skips_csv_header_row() -> None:
    header = (
        "Operation date;Payment date;Card number;Status;Operation amount;Transaction currency;"
        "Payment amount;Payment currency;Cashback;Category;MCC;Description;"
        "Bonuses (including cashback);"
        "Rounding to spare coins;Rounded operation amount\n"
    )
    line = '05.07.2026;05.07.2026;*1;OK;-20,00;RUB;-20,00;RUB;;Transport;4111;"Metro";0;0;-20,00\n'
    rows, errors = parse_statement(header + line)
    assert not errors
    assert len(rows) == 1
    assert rows[0]["description"] == "Metro"


def test_parse_statement_bad_line() -> None:
    rows, errors = parse_statement("garbage line\n")
    assert not rows
    assert len(errors) == 1


def test_parse_statement_row_fields() -> None:
    rows, _ = parse_statement(SAMPLE_TSV)
    assert rows[0]["bank_category"] == "Transfers"
    assert rows[0]["mcc"] == ""
    assert rows[0]["description"] == "Sberbank"
    assert rows[1]["bank_category"] == "Supermarkets"
    assert rows[1]["mcc"] == "5411"

    assert rows[0]["card"] == "*2947"

    assert rows[0].hash == ""


def test_tx_hash_is_scoped_to_the_account() -> None:
    a = tx_hash(1, "2026-07-03T19:48:24", -45000, "Sberbank")
    b = tx_hash(2, "2026-07-03T19:48:24", -45000, "Sberbank")
    assert a != b
    assert len(a) == len(b) == 64
    assert a == tx_hash(1, "2026-07-03T19:48:24", -45000, "Sberbank")


def test_parse_statement_semicolon_delimiter_and_quotes() -> None:
    line = '05.07.2026;05.07.2026;*1;OK;-20,00;RUB;-20,00;RUB;;Transport;4111;"Metro";0;0;-20,00\n'
    rows, errors = parse_statement(line)
    assert not errors
    assert len(rows) == 1

    assert rows[0]["description"] == "Metro"
    assert rows[0]["amount"] == -2000


def test_parse_statement_accepts_exactly_twelve_columns() -> None:
    line = (
        "05.07.2026 10:00:00\t05.07.2026\t*1\tOK\t-10,00\tRUB\t-10,00\tRUB\t\t"
        "Cafe\t5812\tStarbucks\n"
    )
    rows, errors = parse_statement(line)
    assert not errors
    assert len(rows) == 1
    assert rows[0]["description"] == "Starbucks"
    assert rows[0]["mcc"] == "5812"


def test_parse_statement_too_few_columns_reports_count_and_line() -> None:
    rows, errors = parse_statement("a;b;c\n")
    assert not rows
    assert len(errors) == 1
    assert errors[0].line == 1
    assert errors[0].error == "expected >=12 columns, got 3"
    assert errors[0].raw == "a;b;c"


def test_parse_statement_error_line_numbers_are_one_based() -> None:

    nodate = "NODATE\t05.07.2026\t*1\tOK\t-10,00\tRUB\t-10,00\tRUB\t\tCafe\t5812\tX"
    rows, errors = parse_statement("\n" + nodate + "\n")
    assert not rows
    assert errors[0]["line"] == 2
    assert errors[0]["error"] == "unparseable date or amount"


def test_parse_statement_needs_both_date_and_amount() -> None:
    valid = "05.07.2026\t05.07.2026\t*1\tOK\t-10,00\tRUB\t-10,00\tRUB\t\tCafe\t5812\tX"
    bad_date = valid.replace("05.07.2026\t05.07.2026", "NODATE\t05.07.2026", 1)
    bad_amount = valid.replace("-10,00\tRUB\t-10,00", "-10,00\tRUB\tNOPE", 1)
    for line in (bad_date, bad_amount):
        rows, errors = parse_statement(line + "\n")
        assert not rows
        assert errors[0]["error"] == "unparseable date or amount"


def test_parse_statement_strips_only_the_surrounding_quotes() -> None:

    line = (
        "05.07.2026 10:00:00\t05.07.2026\t*1\tOK\t-10,00\tRUB\t-10,00\tRUB\t\t"
        "Electronics\t5732\tXerox\n"
    )
    rows, errors = parse_statement(line)
    assert not errors
    assert rows[0]["description"] == "Xerox"


def test_parse_statement_unparseable_error_carries_the_raw_line() -> None:
    nodate = "NODATE\t05.07.2026\t*1\tOK\t-10,00\tRUB\t-10,00\tRUB\t\tCafe\t5812\tX"
    _, errors = parse_statement(nodate + "\n")
    assert errors[0]["raw"] == nodate


def test_parse_statement_continues_after_every_kind_of_skip() -> None:
    valid = "05.07.2026 10:00:00\t05.07.2026\t*1\tOK\t-10,00\tRUB\t-10,00\tRUB\t\tCafe\t5812\tGOOD"
    failed = valid.replace("\tOK\t", "\tFAILED\t").replace("GOOD", "SKIP")
    bad_date = valid.replace("05.07.2026 10:00:00", "NODATE", 1).replace("GOOD", "BADDATE")
    text = f"\na;b\n{failed}\n{bad_date}\n{valid}" + "\n"
    rows, errors = parse_statement(text)

    assert [r["description"] for r in rows] == ["GOOD"]

    assert len(errors) == 2


def test_categorize_first_rule_wins_and_sign_split() -> None:
    groups = {1: "expense", 2: "income"}
    cats: list[CategoryDefinition] = [
        CategoryDefinition(10, "Groceries", "Pyaterochka|Lenta", 1),
        CategoryDefinition(11, "Entertainment", "Lenta", 1),
        CategoryDefinition(20, "Cashback", "Cashback", 2),
    ]
    rules = build_rules(cats, groups)
    assert categorize("Pyaterochka", -100, rules) == 10
    assert categorize("LENTA", -100, rules) == 10
    assert categorize("Cashback credit", 100, rules) == 20
    assert categorize("Cashback", -100, rules) is None
    assert categorize("", -100, rules) is None


def test_build_rules_skips_empty_bad_kind_and_null_keywords() -> None:
    groups = {1: "expense", 2: "income", 3: "other"}
    cats: list[CategoryDefinition] = [
        CategoryDefinition(1, "NoKw", "", 1),
        CategoryDefinition(2, "BadKind", "x", 3),
        CategoryDefinition(3, "Groceries", "Pyaterochka | Lenta| Lenta", 1),
        CategoryDefinition(4, "Salary", "salary", 2),
        CategoryDefinition(5, "NullKw", None, 1),
    ]
    rules = build_rules(cats, groups)

    assert [r.category_id for r in rules["OUT"]] == [3]
    assert [r.category_id for r in rules["IN"]] == [4]
    assert rules["OUT"][0].name == "Groceries"

    assert rules["OUT"][0].keywords == ["pyaterochka", "lenta"]


def test_categorize_guards_on_empty_desc_and_zero_amount() -> None:
    groups = {1: "expense", 2: "income"}
    cats: list[CategoryDefinition] = [
        CategoryDefinition(10, "Cafe", "cafe", 1),
        CategoryDefinition(20, "Salary", "salary", 2),
        CategoryDefinition(30, "Decoy", "xx", 1),
    ]
    rules = build_rules(cats, groups)
    assert categorize("Cafe Pushkin", -500, rules) == 10
    assert categorize("Salary", 500, rules) == 20

    assert categorize("Cafe", 0, rules) is None

    assert categorize("Salary", 1, rules) == 20

    assert categorize("", -500, rules) is None


def test_categorize_files_a_refund_back_into_its_expense_envelope() -> None:
    """
    A merchant's money coming back is a refund: it must land in the envelope.

    it left, not drift to uncategorized where the budget cannot see it. Income.
    keywords still win first, so a real inflow is never mistaken for a refund.
    """
    groups = {1: "expense", 2: "income"}
    cats: list[CategoryDefinition] = [
        CategoryDefinition(10, "Groceries", "Pyaterochka", 1),
        CategoryDefinition(20, "Cashback", "Cashback|pyaterochka cashback", 2),
    ]
    rules = build_rules(cats, groups)
    assert categorize("Pyaterochka refund", 8470, rules) == 10
    assert categorize("Pyaterochka cashback", 100, rules) == 20
    assert categorize("Transfer from mom", 5000, rules) is None
    assert categorize("Pyaterochka", -100, rules) == 10
