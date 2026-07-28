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


def test_day_number_is_days_since_the_unix_epoch():
    # absolute values, not just gaps: the epoch offset, the era multiplier and
    # the year-of-era arithmetic all cancel out of a difference and only show
    # here
    assert day_number("1970-01-01") == 0
    assert day_number("1970-01-02") == 1
    assert day_number("1969-12-31") == -1
    assert day_number("2000-01-01") == 10957
    # a year that drives the era term negative (0000-01-01 shifts to y = -1)
    assert day_number("0000-01-01") == -719528


def test_pairs_opposite_amounts_on_different_accounts():
    pairs = find_pairs([row(1, 10, -5000, 1), row(2, 10, 5000, 2)])
    assert pairs == [
        {"outTxId": 1, "inTxId": 2, "amount": 5000, "days": 0, "hint": False, "mismatch": False}
    ]


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


def test_a_purchase_matching_a_transfer_leg_is_never_merged_on_its_own():
    """
    A transfer's inflow whose true outflow sits on the same account (and so can
    never pair) must not swallow an unrelated purchase that happens to match the
    amount — one leg saying "transfer" while the other names a merchant is a
    question for the user, not a merge.
    """
    rows = [
        row(1, 10, -100000, 1, description="IP Elyan A.Kh"),
        row(2, 10, 100000, 2, description="Между своими счетами"),
    ]
    pairs = find_pairs(rows)
    assert len(pairs) == 1
    assert pairs[0]["mismatch"] is True
    auto, suggested = split_confident(pairs)
    assert auto == []
    assert suggested == pairs


def test_a_hinted_leg_with_a_silent_partner_still_merges():
    # banks often leave one leg's description blank; that is absence of
    # evidence, not a contradiction
    rows = [
        row(1, 10, -100000, 1, description=""),
        row(2, 10, 100000, 2, description="Перевод между своими счетами"),
    ]
    pairs = find_pairs(rows)
    assert pairs[0]["mismatch"] is False
    auto, suggested = split_confident(pairs)
    assert auto == pairs
    assert suggested == []


def test_both_legs_hinted_beat_a_mismatched_pair_at_the_same_distance():
    rows = [
        row(1, 10, -100000, 1, description="Перевод СБП"),
        row(2, 10, -100000, 2, description="Ресторан У Луки"),
        row(3, 10, 100000, 3, description="Пополнение. Перевод между своими"),
    ]
    pairs = find_pairs(rows)
    assert [(p["outTxId"], p["inTxId"]) for p in pairs] == [(1, 3)]
    assert pairs[0]["mismatch"] is False


def test_two_silent_legs_still_merge_by_amount_and_day():
    rows = [row(1, 10, -5000, 1), row(2, 10, 5000, 2)]
    auto, suggested = split_confident(find_pairs(rows))
    assert len(auto) == 1
    assert suggested == []
