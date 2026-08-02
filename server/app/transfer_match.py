"""
Pairing rule for transfers: find the two rows that are the same money leaving.

one account and arriving on another.

Pure functions over transfer records — no database, no I/O — so the rule can be
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

from collections.abc import Iterable
from dataclasses import dataclass

AUTO_DAYS = 1
SUGGEST_DAYS = 5

TRANSFER_HINTS = (
    "перевод",
    "перевела",
    "перевел",
    "между своими",
    "собственные средства",
    "between own accounts",
    "transfer",
    "card2card",
    "c2c",
    "сбп",
    "пополнение",
    "внесение",
    "снятие",
)


@dataclass(frozen=True, slots=True)
class TransferMatchRow:
    """Represent TransferMatchRow."""

    id: int
    date: str
    amount: int
    account_id: int
    description: str = ""
    transfer_id: str | None = None


@dataclass(frozen=True, slots=True)
class TransferCandidate:
    """Represent TransferCandidate."""

    out_tx_id: int
    in_tx_id: int
    amount: int
    days: int
    hint: bool
    mismatch: bool = False


def day_number(date_iso: str) -> int:
    """
    Days since the epoch for an ISO date(time), by calendar day only — the.

    times of the two legs are irrelevant and banks disagree about them anyway.
    """
    y, m, d = (int(p) for p in date_iso[:10].split("-"))

    y -= m <= 2  # noqa: PLR2004
    era = (y if y >= 0 else y - 399) // 400
    yoe = y - era * 400
    doy = (153 * (m + (-3 if m > 2 else 9)) + 2) // 5 + d - 1  # noqa: PLR2004
    doe = yoe * 365 + yoe // 4 - yoe // 100 + doy
    return era * 146097 + doe - 719468


def has_hint(description: str) -> bool:
    """Handle has hint."""
    lowered = description.lower()
    return any(h in lowered for h in TRANSFER_HINTS)


def find_pairs(  # noqa: C901
    rows: Iterable[TransferMatchRow],
    max_days: int = SUGGEST_DAYS,
    rejected: Iterable[tuple[int, int]] = (),
) -> list[TransferCandidate]:
    """
    Greedily pair ``rows`` into transfer candidates.

    Rows already in a transfer are skipped. ``rejected`` contains pairs the
    user has dismissed. Results are sorted best-first: closest in time,
    transfer-sounding descriptions ahead of silent ones, then by id.
    """
    rejected = {(int(p[0]), int(p[1])) for p in rejected}
    outs: dict[int, list[TransferMatchRow]] = {}
    ins: dict[int, list[TransferMatchRow]] = {}
    for r in rows:
        if r.transfer_id:
            continue
        amount = r.amount
        if amount == 0:
            continue
        bucket = outs if amount < 0 else ins
        bucket.setdefault(abs(amount), []).append(r)

    candidates: list[TransferCandidate] = []
    for amount, out_rows in outs.items():
        in_rows = ins.get(amount)
        if not in_rows:
            continue
        for out_row in out_rows:
            out_day = day_number(out_row.date)
            for in_row in in_rows:
                if out_row.account_id == in_row.account_id:
                    continue
                if (out_row.id, in_row.id) in rejected:
                    continue
                days = abs(day_number(in_row.date) - out_day)
                if days > max_days:
                    continue
                out_hint = has_hint(out_row.description)
                in_hint = has_hint(in_row.description)
                silent = (in_row if out_hint else out_row).description
                candidates.append(
                    TransferCandidate(
                        out_tx_id=out_row.id,
                        in_tx_id=in_row.id,
                        amount=amount,
                        days=days,
                        hint=out_hint or in_hint,
                        mismatch=out_hint != in_hint and bool(silent.strip()),
                    ),
                )

    candidates.sort(key=lambda c: (c.days, c.mismatch, not c.hint, c.out_tx_id, c.in_tx_id))
    used = set()
    pairs = []
    for c in candidates:
        if c.out_tx_id in used or c.in_tx_id in used:
            continue
        used.add(c.out_tx_id)
        used.add(c.in_tx_id)
        pairs.append(c)
    return pairs


def split_confident(
    pairs: Iterable[TransferCandidate],
    auto_days: int = AUTO_DAYS,
) -> tuple[list[TransferCandidate], list[TransferCandidate]]:
    """
    Partition matched pairs into the ones safe to merge without asking.

    (``days <= auto_days`` and no description mismatch) and the ones worth.
    showing as suggestions.
    """
    auto: list[TransferCandidate] = []
    suggested: list[TransferCandidate] = []
    for p in pairs:
        confident = p.days <= auto_days and not p.mismatch
        (auto if confident else suggested).append(p)
    return auto, suggested
