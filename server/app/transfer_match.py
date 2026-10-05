"""
Pairing rule for transfers: find the two rows that are the same money leaving
one account and arriving on another.

Pure functions over plain dicts — no database, no I/O — so the rule can be
tested on its own and reused by the manual import, the connector sync and the
on-demand rescan without drifting between them.

A candidate pair is an outflow and an inflow that

* sit on two different accounts of the same user,
* have exactly opposite amounts (a fee makes the legs unequal; those are left
  for the user to link by hand rather than guessed at),
* fall within ``max_days`` of each other,
* are both still unattached to any transfer, and
* have not already been dismissed as "not a transfer".

Matching is greedy over candidates ordered by how close they are, and every
transaction is used at most once, so the result is deterministic.

A pair where one leg reads as a transfer but the other carries an unrelated
description — a merchant purchase that merely matches the amount — is a
mismatch: still offered as a suggestion, never merged on its own.
"""

from typing import Any, Iterable, Literal, TypeVar, cast

AUTO_DAYS: Literal[1] = 1
SUGGEST_DAYS: Literal[5] = 5

TRANSFER_HINTS = (
    "перевод",
    "перевела",
    "перевел",
    "между своими",
    "собственные средства",
    "transfer",
    "card2card",
    "c2c",
    "сбп",
    "пополнение",
    "внесение",
    "снятие",
)

_T = TypeVar("_T")

RowKey = Literal["id", "date", "amount", "account_id", "description", "transfer_id"]


def day_number(date_iso: str, /) -> int:
    """
    Days since the epoch for an ISO date(time), by calendar day only — the
    times of the two legs are irrelevant and banks disagree about them anyway.
    """
    y, m, d = (int(p) for p in date_iso[:10].split("-"))
    y -= m <= 2
    era = (y if y >= 0 else y - 399) // 400
    yoe = y - era * 400
    doy = (153 * (m + (-3 if m > 2 else 9)) + 2) // 5 + d - 1
    doe = yoe * 365 + yoe // 4 - yoe // 100 + doy
    return era * 146097 + doe - 719468


def field(row: Any, name: RowKey, default: _T) -> _T:
    """
    Read ``name`` off a dict or a ``sqlite3.Row``, neither of which shares the
    other's accessor for a missing key.
    """
    try:
        value = row[name]
    except (KeyError, IndexError):
        return default
    return default if value is None else cast(_T, value)


def has_hint(description: str | None) -> bool:
    lowered = (description or "").lower()
    return any(h in lowered for h in TRANSFER_HINTS)


class TransferPair(dict[str, object]):
    outTxId: int
    inTxId: int
    amount: int
    days: int
    hint: bool
    mismatch: bool


def find_pairs(
    rows: list[Any],
    max_days: int = SUGGEST_DAYS,
    rejected: Iterable[tuple[int, int]] = (),
) -> list[TransferPair]:
    """
    Greedily pair ``rows`` into transfer candidates.

    ``rows`` are dicts (or sqlite rows) carrying ``id``, ``date``, ``amount``,
    ``account_id`` and optionally ``description`` and ``transfer_id``. Rows
    already in a transfer are skipped. ``rejected`` is an iterable of
    ``(out_id, in_id)`` pairs the user has dismissed.

    Returns a list of ``{"outTxId", "inTxId", "amount", "days", "hint"}``
    sorted best-first: closest in time, transfer-sounding descriptions ahead of
    silent ones, then by id so the order never depends on the input order.
    """
    rejected_set: set[tuple[int, int]] = set(rejected)
    outs: dict[int, list[Any]] = {}
    ins: dict[int, list[Any]] = {}
    for r in rows:
        if field(r, "transfer_id", None):
            continue
        amount = cast(int, r["amount"])
        if amount == 0:
            continue
        bucket = outs if amount < 0 else ins
        bucket.setdefault(abs(amount), []).append(r)

    candidates: list[TransferPair] = []
    for amount, out_rows in outs.items():
        in_rows = ins.get(amount)
        if not in_rows:
            continue
        for out_row in out_rows:
            out_day = day_number(cast(str, out_row["date"]))
            for in_row in in_rows:
                if out_row["account_id"] == in_row["account_id"]:
                    continue
                if (cast(int, out_row["id"]), cast(int, in_row["id"])) in rejected_set:
                    continue
                days = abs(day_number(cast(str, in_row["date"])) - out_day)
                if days > max_days:
                    continue
                out_hint = has_hint(cast(str | None, field(out_row, "description", "")))
                in_hint = has_hint(cast(str | None, field(in_row, "description", "")))
                silent = cast(str | None, field(in_row if out_hint else out_row, "description", ""))
                candidates.append(
                    TransferPair(
                        {
                            "outTxId": cast(int, out_row["id"]),
                            "inTxId": cast(int, in_row["id"]),
                            "amount": amount,
                            "days": days,
                            "hint": out_hint or in_hint,
                            "mismatch": out_hint != in_hint and bool(str(silent).strip()),
                        }
                    )
                )

    candidates.sort(
        key=lambda c: (c["days"], c["mismatch"], not c["hint"], c["outTxId"], c["inTxId"])
    )
    used: set[int] = set()
    pairs: list[TransferPair] = []
    for c in candidates:
        if c["outTxId"] in used or c["inTxId"] in used:
            continue
        used.add(c["outTxId"])
        used.add(c["inTxId"])
        pairs.append(c)
    return pairs


def split_confident(
    pairs: list[Any], auto_days: int = AUTO_DAYS
) -> tuple[list[TransferPair], list[TransferPair]]:
    """
    Partition matched pairs into the ones safe to merge without asking
    (``days <= auto_days`` and no description mismatch) and the ones worth
    showing as suggestions.
    """
    auto: list[TransferPair] = []
    suggested: list[TransferPair] = []
    for p in pairs:
        confident = cast(int, p["days"]) <= auto_days and not cast(bool, p.get("mismatch"))
        (auto if confident else suggested).append(p)
    return auto, suggested
