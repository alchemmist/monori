import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

import app.db as dbmod
from app.money import (
    account_currency,
    base_currency,
    base_currency_of_account,
    reprice_user,
    resolve_currency,
    to_base,
)
from app.rates import store_rates


def _db(tmp_path, base="RUB"):
    c = dbmod.connect(str(tmp_path / "money.db"))
    c.execute(
        "INSERT INTO users (email, email_canonical, password_hash, created_at, base_currency)"
        " VALUES ('u@e.co', 'u@e.co', 'h', 't', ?)",
        (base,),
    )
    uid = c.execute("SELECT id FROM users").fetchone()[0]
    for name, currency in (("Rubles", "RUB"), ("Lari", "GEL")):
        c.execute(
            "INSERT INTO accounts (user_id, name, type, currency, sort)"
            " VALUES (?, ?, 'card', ?, 1)",
            (uid, name, currency),
        )
    c.commit()
    return c, uid


def _account(c, name):
    return c.execute("SELECT id FROM accounts WHERE name=?", (name,)).fetchone()[0]


def _add_tx(c, account_id, amount, currency, date="2026-07-01T10:00:00", base=None):
    c.execute(
        "INSERT INTO transactions (date, amount, currency, base_amount, description,"
        " account_id, hash, source) VALUES (?, ?, ?, ?, 'x', ?, ?, 'manual')",
        (date, amount, currency, amount if base is None else base, account_id, f"h{amount}"),
    )
    return c.execute("SELECT MAX(id) FROM transactions").fetchone()[0]


def test_reads_the_currency_off_an_account_and_its_owner(tmp_path):
    c, uid = _db(tmp_path, base="EUR")
    try:
        lari = _account(c, "Lari")
        assert account_currency(c, lari) == "GEL"
        assert base_currency(c, uid) == "EUR"
        assert base_currency_of_account(c, lari) == "EUR"
    finally:
        c.close()


def test_missing_rows_fall_back_to_rubles(tmp_path):
    c, _ = _db(tmp_path)
    try:
        assert account_currency(c, 9999) == "RUB"
        assert base_currency(c, 9999) == "RUB"
        assert base_currency_of_account(c, 9999) == "RUB"
    finally:
        c.close()


def test_resolve_currency_prefers_what_was_asked_for(tmp_path):
    c, _ = _db(tmp_path)
    try:
        rubles = _account(c, "Rubles")
        assert resolve_currency(c, rubles, "usd") == "USD"
        assert resolve_currency(c, rubles, None) == "RUB"
        assert resolve_currency(c, _account(c, "Lari"), "") == "GEL"
    finally:
        c.close()


def test_to_base_converts_at_the_rate_for_the_date(tmp_path):
    c, _ = _db(tmp_path)
    try:
        store_rates(c, "2026-07-01", {"GEL": 30.0})
        assert to_base(c, -10000, "GEL", "RUB", "2026-07-01T10:00:00") == -300000
    finally:
        c.close()


def test_to_base_carries_an_unquotable_currency_across_at_face_value(tmp_path):
    """
    A rate feed being unreachable must not be able to block a write. The number
    is wrong until rates arrive, and repricing then corrects it.
    """
    c, _ = _db(tmp_path)
    try:
        assert to_base(c, 5000, "XYZ", "RUB", "2026-07-01") == 5000
    finally:
        c.close()


def test_reprice_only_touches_what_moved(tmp_path):
    c, uid = _db(tmp_path)
    try:
        store_rates(c, "2026-07-01", {"GEL": 30.0})
        rubles, lari = _account(c, "Rubles"), _account(c, "Lari")
        _add_tx(c, rubles, -5000, "RUB")
        gel_tx = _add_tx(c, lari, -10000, "GEL")
        assert reprice_user(c, uid) == 1
        assert (
            c.execute("SELECT base_amount FROM transactions WHERE id=?", (gel_tx,)).fetchone()[0]
            == -300000
        )
        # a second pass has nothing left to correct
        assert reprice_user(c, uid) == 0
    finally:
        c.close()


def test_reprice_follows_a_new_reporting_currency(tmp_path):
    c, uid = _db(tmp_path)
    try:
        store_rates(c, "2026-07-01", {"GEL": 30.0, "USD": 90.0})
        lari = _account(c, "Lari")
        gel_tx = _add_tx(c, lari, -30000, "GEL")
        c.execute("UPDATE users SET base_currency='USD' WHERE id=?", (uid,))
        reprice_user(c, uid)
        # 300.00 GEL = 9000 RUB = 100.00 USD
        assert (
            c.execute("SELECT base_amount FROM transactions WHERE id=?", (gel_tx,)).fetchone()[0]
            == -10000
        )
    finally:
        c.close()


def test_reprice_uses_each_row_own_date(tmp_path):
    c, uid = _db(tmp_path)
    try:
        store_rates(c, "2026-01-01", {"GEL": 30.0})
        store_rates(c, "2026-07-01", {"GEL": 40.0})
        lari = _account(c, "Lari")
        january = _add_tx(c, lari, -10000, "GEL", date="2026-01-15T10:00:00")
        july = _add_tx(c, lari, -20000, "GEL", date="2026-07-15T10:00:00")
        reprice_user(c, uid)
        amounts = dict(
            c.execute(
                "SELECT id, base_amount FROM transactions WHERE id IN (?, ?)", (january, july)
            )
        )
        assert amounts[january] == -300000
        assert amounts[july] == -800000
    finally:
        c.close()
