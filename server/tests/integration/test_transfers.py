import pytest

pytestmark = pytest.mark.integration


def legs(api, transfer_id):
    return [t for t in api.snapshot()["transactions"] if t["transferId"] == transfer_id]


def pair(api, out_account, in_account, amount=5000, out_date="2026-03-10", in_date="2026-03-10"):
    """
    Two ordinary transactions that together look like a transfer, as a bank
    would deliver them: nothing links them yet.
    """
    out_id = api.tx(f"{out_date}T09:00:00", -amount, accountId=out_account)
    in_id = api.tx(f"{in_date}T18:00:00", amount, accountId=in_account)
    return out_id, in_id


def test_transfer_creates_linked_pair(api):
    a = api.default_account()
    b = api.account("Vault")
    transfer_id = api.transfer(a, b, 5000, comment="move")

    rows = legs(api, transfer_id)
    assert len(rows) == 2
    assert {t["accountId"]: t["amount"] for t in rows} == {a: -5000, b: 5000}
    assert all(t["categoryId"] is None and t["source"] == "transfer" for t in rows)
    assert sum(t["amount"] for t in rows) == 0


def test_transfer_shows_up_as_an_entity_in_the_snapshot(api):
    a = api.default_account()
    b = api.account("Vault")
    transfer_id = api.transfer(a, b, 5000, comment="move")

    entity = next(t for t in api.snapshot()["transfers"] if t["id"] == transfer_id)
    out_leg, in_leg = (api.tx_by(entity["outTxId"]), api.tx_by(entity["inTxId"]))
    assert out_leg["amount"] == -5000 and out_leg["accountId"] == a
    assert in_leg["amount"] == 5000 and in_leg["accountId"] == b
    assert entity["origin"] == "manual"
    assert entity["note"] == "move"


def test_transfer_rejects_same_account(api, client):
    a = api.default_account()
    r = client.post(
        "/api/transfers",
        json={"fromAccountId": a, "toAccountId": a, "amount": 100, "date": "2026-01-01T00:00:00"},
    )
    assert r.status_code == 400


def test_transfer_rejects_unknown_account(api, client):
    a = api.default_account()
    r = client.post(
        "/api/transfers",
        json={"fromAccountId": a, "toAccountId": 999, "amount": 100, "date": "2026-01-01T00:00:00"},
    )
    assert r.status_code == 400


def test_transfer_rejects_non_positive_amount(api, client):
    a = api.default_account()
    b = api.account("Vault")
    r = client.post(
        "/api/transfers",
        json={"fromAccountId": a, "toAccountId": b, "amount": 0, "date": "2026-01-01T00:00:00"},
    )
    assert r.status_code == 422


def test_link_merges_an_existing_pair_without_touching_the_rows(api, client):
    a = api.default_account()
    b = api.account("Vault")
    out_id, in_id = pair(api, a, b)
    before = (api.tx_by(out_id)["amount"], api.tx_by(in_id)["amount"])

    r = client.post("/api/transfers/link", json={"outTxId": out_id, "inTxId": in_id})
    assert r.status_code == 200, r.text
    transfer_id = r.json()["transferId"]

    assert {t["id"] for t in legs(api, transfer_id)} == {out_id, in_id}
    # both rows survive the merge unchanged, which is what keeps a re-sync from
    # inserting them a second time
    assert (api.tx_by(out_id)["amount"], api.tx_by(in_id)["amount"]) == before
    assert next(t for t in api.snapshot()["transfers"] if t["id"] == transfer_id)["origin"] == (
        "manual"
    )


def test_link_moves_categories_aside_and_split_gives_them_back(api, client):
    g = api.group("Living")
    cat = api.category("Groceries", g)
    a = api.default_account()
    b = api.account("Vault")
    out_id, in_id = pair(api, a, b)
    client.patch(f"/api/transactions/{out_id}", json={"categoryId": cat})

    transfer_id = client.post(
        "/api/transfers/link", json={"outTxId": out_id, "inTxId": in_id}
    ).json()["transferId"]
    assert api.tx_by(out_id)["categoryId"] is None

    assert client.delete(f"/api/transfers/{transfer_id}").status_code == 200
    assert api.tx_by(out_id)["categoryId"] == cat


def test_split_keeps_both_transactions(api, client):
    a = api.default_account()
    b = api.account("Vault")
    transfer_id = api.transfer(a, b, 5000)
    out_id, in_id = (t["id"] for t in sorted(legs(api, transfer_id), key=lambda t: t["amount"]))

    assert client.delete(f"/api/transfers/{transfer_id}").status_code == 200
    assert legs(api, transfer_id) == []
    assert not api.snapshot()["transfers"]
    # the rows themselves are still there, just ordinary again
    assert api.tx_by(out_id)["transferId"] is None
    assert api.tx_by(in_id)["transferId"] is None

    assert client.delete(f"/api/transfers/{transfer_id}").status_code == 404


def test_split_frees_the_legs_to_be_linked_again(api, client):
    a = api.default_account()
    b = api.account("Vault")
    out_id, in_id = pair(api, a, b)
    first = client.post("/api/transfers/link", json={"outTxId": out_id, "inTxId": in_id}).json()
    client.delete(f"/api/transfers/{first['transferId']}")
    second = client.post("/api/transfers/link", json={"outTxId": out_id, "inTxId": in_id})
    assert second.status_code == 200


@pytest.mark.parametrize(
    "amounts, same_account",
    [
        ((-5000, -5000), False),  # two outflows
        ((5000, 5000), False),  # two inflows
        ((-5000, 5000), True),  # one account
    ],
)
def test_link_rejects_pairs_that_are_not_a_transfer(api, client, amounts, same_account):
    a = api.default_account()
    b = a if same_account else api.account("Vault")
    out_id = api.tx("2026-03-10T09:00:00", amounts[0], accountId=a)
    in_id = api.tx("2026-03-10T18:00:00", amounts[1], accountId=b)
    r = client.post("/api/transfers/link", json={"outTxId": out_id, "inTxId": in_id})
    assert r.status_code == 400


def test_link_rejects_a_leg_already_in_a_transfer(api, client):
    a = api.default_account()
    b = api.account("Vault")
    third = api.account("Pocket")
    out_id, in_id = pair(api, a, b)
    client.post("/api/transfers/link", json={"outTxId": out_id, "inTxId": in_id})
    other = api.tx("2026-03-10T18:00:00", 5000, accountId=third)
    r = client.post("/api/transfers/link", json={"outTxId": out_id, "inTxId": other})
    assert r.status_code == 400


def test_link_rejects_another_users_transaction(api, client):
    from conftest import login_as

    a = api.default_account()
    b = api.account("Vault")
    out_id, in_id = pair(api, a, b)
    client.headers.update(login_as(client, "other@example.com"))
    r = client.post("/api/transfers/link", json={"outTxId": out_id, "inTxId": in_id})
    assert r.status_code == 400


def test_detect_merges_a_same_day_pair(api, client):
    a = api.default_account()
    b = api.account("Vault")
    out_id, in_id = pair(api, a, b)

    result = client.post("/api/transfers/detect").json()
    assert result["merged"] and result["merged"][0]["outTxId"] == out_id
    assert api.tx_by(in_id)["transferId"] == result["merged"][0]["id"]
    assert next(iter(api.snapshot()["transfers"]))["origin"] == "matched"


def test_detect_leaves_a_distant_pair_as_a_suggestion(api, client):
    a = api.default_account()
    b = api.account("Vault")
    out_id, in_id = pair(api, a, b, out_date="2026-03-10", in_date="2026-03-13")

    result = client.post("/api/transfers/detect").json()
    assert result["merged"] == []
    assert result["suggested"] == 1

    rows = client.get("/api/transfers/suggestions").json()
    assert [(p["outTxId"], p["inTxId"]) for p in rows["rows"]] == [(out_id, in_id)]
    assert {t["id"] for t in rows["transactions"]} == {out_id, in_id}


def test_dismissed_suggestions_stop_coming_back(api, client):
    a = api.default_account()
    b = api.account("Vault")
    out_id, in_id = pair(api, a, b, out_date="2026-03-10", in_date="2026-03-13")

    client.post("/api/transfers/suggestions/dismiss", json={"outTxId": out_id, "inTxId": in_id})
    assert client.get("/api/transfers/suggestions").json()["rows"] == []
    assert client.post("/api/transfers/detect").json()["suggested"] == 0


def test_detect_leaves_a_disagreeing_same_day_pair_as_a_suggestion(api, client):
    """
    An inflow labeled as a transfer whose true counterpart cannot pair (say,
    both legs landed on one account) must not swallow a purchase that merely
    matches the amount — the pair is offered, not merged.
    """
    a = api.default_account()
    b = api.account("Vault")
    out_id = api.tx("2026-03-10T09:00:00", -100000, accountId=a, description="IP Elyan A.Kh")
    in_id = api.tx("2026-03-10T18:00:00", 100000, accountId=b, description="Между своими счетами")

    result = client.post("/api/transfers/detect").json()
    assert result["merged"] == []
    assert result["suggested"] == 1

    rows = client.get("/api/transfers/suggestions").json()
    assert [(p["outTxId"], p["inTxId"]) for p in rows["rows"]] == [(out_id, in_id)]
    assert rows["rows"][0]["mismatch"] is True


def test_detect_is_idempotent(api, client):
    a = api.default_account()
    b = api.account("Vault")
    pair(api, a, b)

    first = client.post("/api/transfers/detect").json()
    second = client.post("/api/transfers/detect").json()
    assert len(first["merged"]) == 1
    assert second["merged"] == []
    assert len(api.snapshot()["transfers"]) == 1


def test_transfers_list_is_scoped_to_the_user(api, client):
    a = api.default_account()
    b = api.account("Vault")
    api.transfer(a, b, 5000)
    assert len(client.get("/api/transfers").json()["rows"]) == 1

    from conftest import login_as

    client.headers.update(login_as(client, "stranger@example.com"))
    assert client.get("/api/transfers").json()["rows"] == []


def test_deleting_one_leg_leaves_no_dangling_transfer_pointer(api, client):
    a = api.default_account()
    b = api.account("Vault")
    transfer_id = api.transfer(a, b, 5000)
    out_id, in_id = (t["id"] for t in sorted(legs(api, transfer_id), key=lambda t: t["amount"]))

    assert client.delete(f"/api/transactions/{out_id}").status_code == 200

    snap = api.snapshot()
    assert snap["transfers"] == []
    survivor = next(t for t in snap["transactions"] if t["id"] == in_id)
    assert survivor["transferId"] is None


def test_bulk_delete_of_one_leg_also_frees_the_other(api, client):
    a = api.default_account()
    b = api.account("Vault")
    transfer_id = api.transfer(a, b, 5000)
    out_id, in_id = (t["id"] for t in sorted(legs(api, transfer_id), key=lambda t: t["amount"]))

    r = client.post("/api/transactions/bulk", json={"action": "delete", "ids": [out_id]})
    assert r.status_code == 200

    snap = api.snapshot()
    assert snap["transfers"] == []
    assert next(t for t in snap["transactions"] if t["id"] == in_id)["transferId"] is None


def test_deleting_a_leg_restores_the_partner_category(api, client):
    a = api.default_account()
    b = api.account("Vault")
    group = api.group("Daily")
    cat = api.category("Groceries", group)
    out_id, in_id = pair(api, a, b)
    client.patch(f"/api/transactions/{in_id}", json={"categoryId": cat})
    assert (
        client.post("/api/transfers/link", json={"outTxId": out_id, "inTxId": in_id}).status_code
        == 200
    )

    client.delete(f"/api/transactions/{out_id}")

    survivor = next(t for t in api.snapshot()["transactions"] if t["id"] == in_id)
    assert survivor["categoryId"] == cat


def test_detection_never_pairs_a_reconcile_adjustment(api, client):
    """
    A reconcile adjustment is bookkeeping: it exists to bend a balance to the
    bank's figure, not because money moved anywhere. Matching it against a
    real transaction would merge fiction with fact.
    """
    a = api.default_account()
    b = api.account("Vault")
    api.tx("2026-03-10T09:00:00", -5000, accountId=a)
    r = client.post(f"/api/accounts/{b}/reconcile", json={"actualBalance": 5000})
    assert r.status_code == 200 and r.json()["delta"] == 5000

    result = client.post("/api/transfers/detect").json()
    assert result["merged"] == []
    assert result["suggested"] == 0
    assert client.get("/api/transfers/suggestions").json()["rows"] == []
