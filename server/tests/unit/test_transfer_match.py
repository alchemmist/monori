from app.transfer_match import day_number, find_pairs, has_hint, split_confident


def row(tx_id, day, amount, account, description="", transfer_id=None):
    return {
        "id": tx_id,
        "date": f"2026-03-{day:02d}T12:00:00",
        "amount": amount,
        "account_id": account,
        "description": description,
        "transfer_id": transfer_id,
    }


def test_day_number_counts_calendar_days():
    assert day_number("2026-03-02T23:59:00") - day_number("2026-03-01T00:01:00") == 1
    assert day_number("2026-01-01") - day_number("2025-12-31") == 1
    # a leap day must not shift the count
    assert day_number("2024-03-01") - day_number("2024-02-28") == 2


def test_pairs_opposite_amounts_on_different_accounts():
    pairs = find_pairs([row(1, 10, -5000, 1), row(2, 10, 5000, 2)])
    assert pairs == [{"outTxId": 1, "inTxId": 2, "amount": 5000, "days": 0, "hint": False}]


def test_same_account_is_not_a_transfer():
    assert find_pairs([row(1, 10, -5000, 1), row(2, 10, 5000, 1)]) == []


def test_unequal_amounts_never_match():
    # a fee makes the legs differ; those are left for the user to link by hand
    assert find_pairs([row(1, 10, -5000, 1), row(2, 10, 4950, 2)]) == []


def test_pairs_outside_the_window_are_dropped():
    rows = [row(1, 1, -5000, 1), row(2, 10, 5000, 2)]
    assert find_pairs(rows, max_days=5) == []
    assert len(find_pairs(rows, max_days=9)) == 1


def test_rows_already_in_a_transfer_are_skipped():
    rows = [row(1, 10, -5000, 1, transfer_id="abc"), row(2, 10, 5000, 2)]
    assert find_pairs(rows) == []


def test_rejected_pairs_are_not_offered_again():
    rows = [row(1, 10, -5000, 1), row(2, 10, 5000, 2)]
    assert find_pairs(rows, rejected=[(1, 2)]) == []


def test_each_transaction_is_used_at_most_once():
    # one outflow, two possible inflows: the closer one wins and the other is left
    rows = [row(1, 10, -5000, 1), row(2, 10, 5000, 2), row(3, 13, 5000, 3)]
    pairs = find_pairs(rows)
    assert [(p["outTxId"], p["inTxId"]) for p in pairs] == [(1, 2)]


def test_a_transfer_sounding_description_breaks_the_tie():
    rows = [
        row(1, 10, -5000, 1),
        row(2, 10, 5000, 2),
        row(3, 10, 5000, 3, description="Перевод между своими счетами"),
    ]
    pairs = find_pairs(rows)
    assert [(p["outTxId"], p["inTxId"]) for p in pairs] == [(1, 3)]
    assert pairs[0]["hint"] is True


def test_matching_does_not_depend_on_row_order():
    rows = [row(1, 10, -5000, 1), row(2, 11, 5000, 2), row(3, 10, 5000, 3)]
    assert find_pairs(rows) == find_pairs(list(reversed(rows)))


def test_has_hint_is_case_insensitive():
    assert has_hint("ПЕРЕВОД СБП")
    assert has_hint("Transfer to savings")
    assert not has_hint("Lenta groceries")


def test_split_confident_separates_by_distance():
    auto, suggested = split_confident([{"days": 0}, {"days": 1}, {"days": 4}], auto_days=1)
    assert auto == [{"days": 0}, {"days": 1}]
    assert suggested == [{"days": 4}]
