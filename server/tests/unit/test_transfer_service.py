# Copyright (c) 2026
"""Behavioral coverage for ledger transfer operations without an HTTP server."""

import sqlite3
from collections.abc import Iterator
from contextlib import closing
from datetime import datetime, timedelta, timezone, tzinfo
from pathlib import Path

import pytest

from monori.server.app import transfer_service as service
from monori.server.app.transfer_match import TransferCandidate


@pytest.fixture
def ledger() -> Iterator[sqlite3.Connection]:
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys=ON")
    schema = Path(service.__file__).resolve().parent.parent / "schema.sql"
    c.executescript(schema.read_text())
    c.executemany(
        "INSERT INTO users (id, email, email_canonical, password_hash, created_at)"
        " VALUES (?, ?, ?, 'hash', '2026-01-01')",
        [(1, "one@example.com", "one@example.com"), (2, "two@example.com", "two@example.com")],
    )
    c.executemany(
        "INSERT INTO accounts (id, user_id, name) VALUES (?, ?, ?)",
        [(11, 1, "Checking"), (12, 1, "Savings"), (21, 2, "Checking"), (22, 2, "Savings")],
    )
    c.execute(
        "INSERT INTO category_groups (id, user_id, name, sort, type_id)"
        " VALUES (30, 1, 'Spending', 0, 2)",
    )
    c.executemany(
        "INSERT INTO categories (id, group_id, name) VALUES (?, 30, ?)",
        [(31, "Outgoing category"), (32, "Incoming category")],
    )
    try:
        yield c
    finally:
        c.close()


def add_tx(
    c: sqlite3.Connection,
    tx_id: int,
    amount: int,
    account: int,
    **details: str,
) -> int:
    c.execute(
        "INSERT INTO transactions (id, amount, account_id, date, description, hash)"
        " VALUES (?, ?, ?, ?, ?, ?)",
        (
            tx_id,
            amount,
            account,
            details.get("date", "2026-03-10T09:00:00"),
            details.get("description", ""),
            f"hash-{tx_id}",
        ),
    )
    return tx_id


def add_pair(c: sqlite3.Connection) -> service.LinkRequest:
    return service.LinkRequest(add_tx(c, 101, -5000, 11), add_tx(c, 102, 5000, 12))


def tx_state(c: sqlite3.Connection) -> list[tuple[int, int, int | None, str | None]]:
    return [
        tuple(row)
        for row in c.execute(
            "SELECT id, amount, category_id, transfer_id FROM transactions ORDER BY id"
        )
    ]


def test_link_and_split_preserve_legs_categories_and_metadata(
    ledger: sqlite3.Connection,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class LocalClock:
        @staticmethod
        def now(tz: tzinfo | None = None) -> datetime:
            local = datetime(2026, 3, 10, 12, 34, 56, tzinfo=timezone(timedelta(hours=3)))
            return local.replace(tzinfo=None) if tz is None else local.astimezone(tz)

    monkeypatch.setattr(service, "datetime", LocalClock)
    pair = add_pair(ledger)
    ledger.execute("UPDATE transactions SET category_id=31 WHERE id=101")
    ledger.execute("UPDATE transactions SET category_id=32 WHERE id=102")
    service.reject(ledger, 1, 101, 102)
    service.reject(ledger, 1, 102, 101)
    before = tx_state(ledger)

    transfer_id = service.link(ledger, 1, service.LinkRequest(101, 102, note="Move to savings"))

    assert len(transfer_id) == 32
    assert f"{int(transfer_id, 16):032x}" == transfer_id
    assert tx_state(ledger) == [(101, -5000, None, transfer_id), (102, 5000, None, transfer_id)]
    assert service.rejections(ledger, 1) == {(102, 101)}
    [response] = service.list_transfers(ledger, 1)
    assert response.id == transfer_id
    assert (response.out_tx_id, response.in_tx_id) == (pair.out_tx_id, pair.in_tx_id)
    assert (response.origin, response.note) == ("manual", "Move to savings")
    assert response.created_at == "2026-03-10T09:34:56"
    assert service.list_transfers(ledger, 2) == []

    assert service.split(ledger, 2, transfer_id) is False
    assert tx_state(ledger) == [(101, -5000, None, transfer_id), (102, 5000, None, transfer_id)]
    assert service.split(ledger, 1, transfer_id) is True
    assert tx_state(ledger) == before
    assert service.list_transfers(ledger, 1) == []
    assert service.split(ledger, 1, transfer_id) is False
    assert service.link(ledger, 1, pair) != transfer_id


@pytest.mark.parametrize(
    ("out_amount", "in_amount"),
    [(0, 5000), (5000, 5000), (-5000, 0), (-5000, -5000)],
)
def test_link_requires_strict_outflow_and_inflow(
    ledger: sqlite3.Connection,
    out_amount: int,
    in_amount: int,
) -> None:
    add_tx(ledger, 101, out_amount, 11)
    add_tx(ledger, 102, in_amount, 12)
    before = tx_state(ledger)
    with pytest.raises(service.LinkError, match=r"^a transfer needs one outflow and one inflow$"):
        service.link(ledger, 1, service.LinkRequest(101, 102))
    assert tx_state(ledger) == before
    assert service.list_transfers(ledger, 1) == []


@pytest.mark.parametrize("leg", [101, 102])
@pytest.mark.parametrize("foreign", [False, True])
def test_link_and_reject_require_both_owned_legs(
    ledger: sqlite3.Connection,
    leg: int,
    *,
    foreign: bool,
) -> None:
    pair = add_pair(ledger)
    if foreign:
        ledger.execute("UPDATE transactions SET account_id=21 WHERE id=?", (leg,))
    else:
        ledger.execute("DELETE FROM transactions WHERE id=?", (leg,))
    before = tx_state(ledger)
    assert service.owned_tx(ledger, 1, leg) is None
    with pytest.raises(service.LinkError, match=r"^unknown transaction$"):
        service.link(ledger, 1, pair)
    with pytest.raises(service.LinkError, match=r"^unknown transaction$"):
        service.reject(ledger, 1, 101, 102)
    assert service.rejections(ledger, 1) == set()
    assert tx_state(ledger) == before


def test_link_accepts_one_kopeck_and_unequal_manual_legs(ledger: sqlite3.Connection) -> None:
    add_tx(ledger, 101, -2, 11)
    add_tx(ledger, 102, 1, 12)
    transfer_id = service.link(ledger, 1, service.LinkRequest(101, 102))
    assert tx_state(ledger) == [(101, -2, None, transfer_id), (102, 1, None, transfer_id)]


def test_link_rejects_same_account(ledger: sqlite3.Connection) -> None:
    pair = add_pair(ledger)
    ledger.execute("UPDATE transactions SET account_id=11 WHERE id=102")
    with pytest.raises(service.LinkError, match=r"^both legs are on the same account$"):
        service.link(ledger, 1, pair)
    assert service.list_transfers(ledger, 1) == []


@pytest.mark.parametrize("leg", [101, 102])
def test_link_rejects_either_already_linked_leg(ledger: sqlite3.Connection, leg: int) -> None:
    pair = add_pair(ledger)
    ledger.execute("UPDATE transactions SET transfer_id='existing' WHERE id=?", (leg,))
    with pytest.raises(service.LinkError, match=r"^already part of a transfer$"):
        service.link(ledger, 1, pair)
    assert service.list_transfers(ledger, 1) == []


@pytest.mark.parametrize("leg", [101, 102])
def test_link_rejects_either_split_leg(ledger: sqlite3.Connection, leg: int) -> None:
    pair = add_pair(ledger)
    ledger.execute(
        "INSERT INTO splits (transaction_id, category_id, amount) VALUES (?, 31, 5000)",
        (leg,),
    )
    before = tx_state(ledger)
    with pytest.raises(
        service.LinkError, match=r"^split transactions cannot be linked as a transfer$"
    ):
        service.link(ledger, 1, pair)
    assert tx_state(ledger) == before
    assert service.list_transfers(ledger, 1) == []


def test_link_locks_the_ledger_before_reading_either_leg(
    ledger: sqlite3.Connection,
    tmp_path: Path,
) -> None:
    pair = add_pair(ledger)
    ledger.commit()
    path = tmp_path / "ledger.db"
    with closing(sqlite3.connect(path)) as c:
        ledger.backup(c)
    c = sqlite3.connect(path)
    c.row_factory = sqlite3.Row
    competing = sqlite3.connect(path, timeout=0)
    attempted: list[str] = []

    def interleave_write(
        action: int,
        table: str | None,
        _column: str | None,
        _database: str | None,
        _trigger: str | None,
    ) -> int:
        # SQLite authorizes reads before executing them: attempt a concurrent
        # change at that boundary, rather than asserting which SQL was emitted.
        if action == sqlite3.SQLITE_READ and table == "transactions" and not attempted:
            attempted.append("write succeeded")
            try:
                competing.execute("UPDATE transactions SET amount=-6000 WHERE id=101")
                competing.commit()
            except sqlite3.OperationalError as error:
                attempted[0] = str(error)
        return sqlite3.SQLITE_OK

    c.set_authorizer(interleave_write)
    try:
        transfer_id = service.link(c, 1, pair)
        assert attempted == ["database is locked"]
        assert tx_state(c) == [(101, -5000, None, transfer_id), (102, 5000, None, transfer_id)]
    finally:
        c.close()
        competing.close()


def test_link_translates_unique_constraint_failure(ledger: sqlite3.Connection) -> None:
    pair = add_pair(ledger)
    transfer_id = service.link(ledger, 1, pair)
    # Even a stale leg pointer must not bypass the entity's uniqueness constraint.
    ledger.execute("UPDATE transactions SET transfer_id=NULL")
    with pytest.raises(service.LinkError, match=r"^already part of a transfer$") as error:
        service.link(ledger, 1, pair)
    assert isinstance(error.value.__cause__, sqlite3.IntegrityError)
    assert [row.id for row in service.list_transfers(ledger, 1)] == [transfer_id]


@pytest.mark.parametrize("leg", [101, 102])
def test_detach_either_leg_restores_both_and_is_user_scoped(
    ledger: sqlite3.Connection,
    leg: int,
) -> None:
    pair = add_pair(ledger)
    ledger.execute("UPDATE transactions SET category_id=32 WHERE id=102")
    service.link(ledger, 1, pair)
    assert service.detach_leg(ledger, 2, leg) is False
    assert len(service.list_transfers(ledger, 1)) == 1
    assert service.detach_leg(ledger, 1, leg) is True
    assert tx_state(ledger) == [(101, -5000, None, None), (102, 5000, 32, None)]
    assert service.list_transfers(ledger, 1) == []
    assert service.detach_leg(ledger, 1, leg) is False


def test_list_transfers_orders_by_newest_then_id(ledger: sqlite3.Connection) -> None:
    for index, (transfer_id, created) in enumerate(
        [
            ("z-old", "2026-01-01T01:00:00"),
            ("b-new", "2026-02-01T01:00:00"),
            ("a-new", "2026-02-01T01:00:00"),
        ]
    ):
        out_id = add_tx(ledger, 201 + index * 2, -100, 11)
        in_id = add_tx(ledger, 202 + index * 2, 100, 12)
        ledger.execute(
            "INSERT INTO transfers (id, user_id, out_tx_id, in_tx_id, created_at)"
            " VALUES (?, 1, ?, ?, ?)",
            (transfer_id, out_id, in_id, created),
        )
    assert [row.id for row in service.list_transfers(ledger, 1)] == ["a-new", "b-new", "z-old"]


def test_rejections_are_idempotent_user_scoped_and_filter_candidates(
    ledger: sqlite3.Connection,
) -> None:
    add_pair(ledger)
    add_tx(ledger, 201, -7000, 21)
    add_tx(ledger, 202, 7000, 22)
    assert service.candidates(ledger, 1) == [TransferCandidate(101, 102, 5000, 0, hint=False)]
    service.reject(ledger, 1, 101, 102)
    service.reject(ledger, 1, 101, 102)
    service.reject(ledger, 2, 201, 202)
    assert service.rejections(ledger, 1) == {(101, 102)}
    assert service.rejections(ledger, 2) == {(201, 202)}
    assert service.candidates(ledger, 1) == []
    assert service.detect(ledger, 1) == ([], [])


@pytest.mark.parametrize("excluded", ["adjustment", "linked", "foreign"])
@pytest.mark.parametrize("leg", [101, 102])
def test_candidates_exclude_ineligible_legs(
    ledger: sqlite3.Connection,
    excluded: str,
    leg: int,
) -> None:
    add_pair(ledger)
    if excluded == "adjustment":
        ledger.execute("UPDATE transactions SET source='adjustment' WHERE id=?", (leg,))
    elif excluded == "linked":
        ledger.execute("UPDATE transactions SET transfer_id='existing' WHERE id=?", (leg,))
    else:
        ledger.execute("UPDATE transactions SET account_id=21 WHERE id=?", (leg,))
    assert service.candidates(ledger, 1) == []


def test_candidates_honor_day_window_and_preserve_description_hints(
    ledger: sqlite3.Connection,
) -> None:
    add_tx(ledger, 101, -5000, 11, description="transfer")
    add_tx(ledger, 102, 5000, 12, date="2026-03-15T23:00:00", description="transfer")
    expected = TransferCandidate(101, 102, 5000, 5, hint=True)
    assert service.candidates(ledger, 1) == [expected]
    assert service.candidates(ledger, 1, max_days=4) == []
    ledger.execute("UPDATE transactions SET date='2026-03-16' WHERE id=102")
    assert service.candidates(ledger, 1) == []
    assert service.candidates(ledger, 1, max_days=6) == [
        TransferCandidate(101, 102, 5000, 6, hint=True)
    ]


def test_detect_merges_confident_pairs_and_returns_exact_metadata(
    ledger: sqlite3.Connection,
) -> None:
    add_tx(ledger, 101, -5000, 11, description="transfer")
    add_tx(ledger, 102, 5000, 12, date="2026-03-11", description="transfer")
    add_tx(ledger, 103, -7000, 11)
    add_tx(ledger, 104, 7000, 12, date="2026-03-13")
    add_tx(ledger, 105, -9000, 11, description="shop")
    add_tx(ledger, 106, 9000, 12, description="transfer")

    merged, suggested = service.detect(ledger, 1)

    [result] = merged
    assert result == service.MergedTransfer(
        result.id, 5000, 1, hint=True, mismatch=False, out_tx_id=101, in_tx_id=102
    )
    assert suggested == [
        TransferCandidate(105, 106, 9000, 0, hint=True, mismatch=True),
        TransferCandidate(103, 104, 7000, 3, hint=False),
    ]
    [entity] = service.list_transfers(ledger, 1)
    assert (entity.id, entity.out_tx_id, entity.in_tx_id, entity.origin, entity.note) == (
        result.id,
        101,
        102,
        "matched",
        "",
    )
    assert tx_state(ledger)[:2] == [(101, -5000, None, result.id), (102, 5000, None, result.id)]
    assert all(row[3] is None for row in tx_state(ledger)[2:])
    assert service.detect(ledger, 1) == ([], suggested)


def test_detect_honors_custom_auto_and_suggestion_windows(ledger: sqlite3.Connection) -> None:
    add_pair(ledger)
    ledger.execute("UPDATE transactions SET date='2026-03-13' WHERE id=102")
    assert service.detect(ledger, 1, auto_days=3, max_days=2) == ([], [])
    assert service.detect(ledger, 1, auto_days=2, max_days=3) == (
        [],
        [TransferCandidate(101, 102, 5000, 3, hint=False)],
    )
    merged, suggested = service.detect(ledger, 1, auto_days=3, max_days=3)
    assert len(merged) == 1
    assert (merged[0].out_tx_id, merged[0].in_tx_id, merged[0].days) == (101, 102, 3)
    assert suggested == []


def test_detect_skips_unlinkable_pair_and_continues(ledger: sqlite3.Connection) -> None:
    add_pair(ledger)
    add_tx(ledger, 103, -7000, 11)
    add_tx(ledger, 104, 7000, 12)
    ledger.execute(
        "INSERT INTO splits (transaction_id, category_id, amount) VALUES (101, 31, -5000)",
    )
    merged, suggested = service.detect(ledger, 1)
    assert len(merged) == 1
    assert (merged[0].out_tx_id, merged[0].in_tx_id) == (103, 104)
    assert suggested == []
    assert tx_state(ledger)[:2] == [(101, -5000, None, None), (102, 5000, None, None)]
    assert [row.id for row in service.list_transfers(ledger, 1)] == [merged[0].id]
