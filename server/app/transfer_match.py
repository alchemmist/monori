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

from bisect import bisect_left, bisect_right
from collections.abc import Iterable
from dataclasses import dataclass

AUTO_DAYS = 1
SUGGEST_DAYS = 5
FEBRUARY = 2

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

    y -= m <= FEBRUARY
    era = (y if y >= 0 else y - 399) // 400
    yoe = y - era * 400
    doy = (153 * (m + (-3 if m > FEBRUARY else 9)) + 2) // 5 + d - 1
    doe = yoe * 365 + yoe // 4 - yoe // 100 + doy
    return era * 146097 + doe - 719468


def has_hint(description: str) -> bool:
    """Handle has hint."""
    lowered = description.lower()
    return any(h in lowered for h in TRANSFER_HINTS)


def find_pairs(
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
    rejected_pairs = {(int(pair[0]), int(pair[1])) for pair in rejected}
    outs, ins = _transfer_buckets(rows)
    candidates = _transfer_candidates(outs, ins, max_days, rejected_pairs)
    candidates.sort(key=_candidate_sort_key)
    return _select_pairs(candidates)


def _transfer_buckets(
    rows: Iterable[TransferMatchRow],
) -> tuple[dict[int, list[TransferMatchRow]], dict[int, list[TransferMatchRow]]]:
    outs: dict[int, list[TransferMatchRow]] = {}
    ins: dict[int, list[TransferMatchRow]] = {}
    for row in rows:
        if row.transfer_id or row.amount == 0:
            continue
        bucket = outs if row.amount < 0 else ins
        bucket.setdefault(abs(row.amount), []).append(row)
    return outs, ins


def _transfer_candidates(
    outs: dict[int, list[TransferMatchRow]],
    ins: dict[int, list[TransferMatchRow]],
    max_days: int,
    rejected: set[tuple[int, int]],
) -> list[TransferCandidate]:
    candidates: list[TransferCandidate] = []
    for amount, out_rows in outs.items():
        in_rows = ins.get(amount, [])
        dated_ins = sorted(
            ((day_number(row.date), row) for row in in_rows),
            key=lambda item: (item[0], item[1].id),
        )
        in_days = [day for day, _ in dated_ins]
        for out_row in out_rows:
            out_day = day_number(out_row.date)
            start = bisect_left(in_days, out_day - max_days)
            end = bisect_right(in_days, out_day + max_days)
            candidates.extend(
                candidate
                for _, in_row in dated_ins[start:end]
                if (candidate := _transfer_candidate(out_row, in_row, amount, max_days, rejected))
                is not None
            )
    return candidates


def _transfer_candidate(
    out_row: TransferMatchRow,
    in_row: TransferMatchRow,
    amount: int,
    max_days: int,
    rejected: set[tuple[int, int]],
) -> TransferCandidate | None:
    if out_row.account_id == in_row.account_id or (out_row.id, in_row.id) in rejected:
        return None
    days = abs(day_number(in_row.date) - day_number(out_row.date))
    if days > max_days:
        return None
    out_hint = has_hint(out_row.description)
    in_hint = has_hint(in_row.description)
    silent = in_row if out_hint else out_row
    return TransferCandidate(
        out_tx_id=out_row.id,
        in_tx_id=in_row.id,
        amount=amount,
        days=days,
        hint=out_hint or in_hint,
        mismatch=out_hint != in_hint and bool(silent.description.strip()),
    )


def _candidate_sort_key(candidate: TransferCandidate) -> tuple[int, bool, bool, int, int]:
    return (
        candidate.days,
        candidate.mismatch,
        not candidate.hint,
        candidate.out_tx_id,
        candidate.in_tx_id,
    )


def _select_pairs(candidates: Iterable[TransferCandidate]) -> list[TransferCandidate]:
    used: set[int] = set()
    pairs: list[TransferCandidate] = []
    for candidate in candidates:
        if candidate.out_tx_id in used or candidate.in_tx_id in used:
            continue
        used.add(candidate.out_tx_id)
        used.add(candidate.in_tx_id)
        pairs.append(candidate)
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
