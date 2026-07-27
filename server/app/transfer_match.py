"""
Pairing rule for transfers: find the two rows that are the same money leaving
one account and arriving on another.

Pure functions over plain dicts — no database, no I/O — so the rule can be
tested on its own and reused by the manual import, the connector sync and the
on-demand rescan without drifting between them.

A candidate pair is an outflow and an inflow that

* sit on two different accounts of the same user,
* have exactly opposite amounts in the same currency (a fee, or a conversion
  between two currencies, makes the legs unequal; those are left for the user to
  link by hand rather than guessed at),
* fall within ``max_days`` of each other,
* are both still unattached to any transfer, and
* have not already been dismissed as "not a transfer".

Matching is greedy over candidates ordered by how close they are, and every
transaction is used at most once, so the result is deterministic.

A pair where one leg reads as a transfer but the other carries an unrelated
description — a merchant purchase that merely matches the amount — is a
mismatch: still offered as a suggestion, never merged on its own.
"""

from .currencies import DEFAULT_CURRENCY

AUTO_DAYS = 1
SUGGEST_DAYS = 5

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


def day_number(date_iso):
    """
    Days since the epoch for an ISO date(time), by calendar day only — the
    times of the two legs are irrelevant and banks disagree about them anyway.
    """
    y, m, d = (int(p) for p in date_iso[:10].split("-"))
    # Howard Hinnant's days_from_civil, so no datetime import for a hot loop
    y -= m <= 2
    era = (y if y >= 0 else y - 399) // 400
    yoe = y - era * 400
    doy = (153 * (m + (-3 if m > 2 else 9)) + 2) // 5 + d - 1
    doe = yoe * 365 + yoe // 4 - yoe // 100 + doy
    return era * 146097 + doe - 719468


def field(row, name, default=None):
    """
    Read ``name`` off a dict or a ``sqlite3.Row``, neither of which shares the
    other's accessor for a missing key.
    """
    try:
        value = row[name]
    except (KeyError, IndexError):
        return default
    return default if value is None else value


def has_hint(description):
    lowered = (description or "").lower()
    return any(h in lowered for h in TRANSFER_HINTS)


def find_pairs(rows, max_days=SUGGEST_DAYS, rejected=()):
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
    rejected = {tuple(p) for p in rejected}
    outs: dict[tuple, list] = {}
    ins: dict[tuple, list] = {}
    for r in rows:
        if field(r, "transfer_id"):
            continue
        amount = r["amount"]
        if amount == 0:
            continue
        # the currency is part of the bucket key: 100 lari leaving one account
        # and 100 rubles arriving on another are not the same money
        key = (field(r, "currency", DEFAULT_CURRENCY), abs(amount))
        bucket = outs if amount < 0 else ins
        bucket.setdefault(key, []).append(r)

    candidates = []
    for key, out_rows in outs.items():
        in_rows = ins.get(key)
        if not in_rows:
            continue
        amount = key[1]
        for out_row in out_rows:
            out_day = day_number(out_row["date"])
            for in_row in in_rows:
                if out_row["account_id"] == in_row["account_id"]:
                    continue
                if (out_row["id"], in_row["id"]) in rejected:
                    continue
                days = abs(day_number(in_row["date"]) - out_day)
                if days > max_days:
                    continue
                out_hint = has_hint(field(out_row, "description", ""))
                in_hint = has_hint(field(in_row, "description", ""))
                silent = field(in_row if out_hint else out_row, "description", "")
                candidates.append(
                    {
                        "outTxId": out_row["id"],
                        "inTxId": in_row["id"],
                        "amount": amount,
                        "currency": key[0],
                        "days": days,
                        "hint": out_hint or in_hint,
                        # one leg says "transfer", the other names something else
                        # entirely — the amount agreeing is not enough to be sure
                        "mismatch": out_hint != in_hint and bool(str(silent).strip()),
                    }
                )

    candidates.sort(
        key=lambda c: (c["days"], c["mismatch"], not c["hint"], c["outTxId"], c["inTxId"])
    )
    used = set()
    pairs = []
    for c in candidates:
        if c["outTxId"] in used or c["inTxId"] in used:
            continue
        used.add(c["outTxId"])
        used.add(c["inTxId"])
        pairs.append(c)
    return pairs


def split_confident(pairs, auto_days=AUTO_DAYS):
    """
    Partition matched pairs into the ones safe to merge without asking
    (``days <= auto_days`` and no description mismatch) and the ones worth
    showing as suggestions.
    """
    auto: list = []
    suggested: list = []
    for p in pairs:
        confident = p["days"] <= auto_days and not p.get("mismatch")
        (auto if confident else suggested).append(p)
    return auto, suggested
