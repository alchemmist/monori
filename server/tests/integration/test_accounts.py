import pytest
from fastapi.testclient import TestClient

from tests.conftest import Api

pytestmark = pytest.mark.integration


def test_default_account_exists(api: Api) -> None:
    accounts = api.snapshot()["accounts"]
    assert [a["name"] for a in accounts] == ["Cash"]
    assert accounts[0]["type"] == "cash" and accounts[0]["currency"] == "RUB"


def test_account_crud_and_uniqueness(api: Api, client: TestClient) -> None:
    cash = api.account("Vault", type="cash", icon="ruble", openingBalance=5000)
    row = api.acct(cash)
    assert row["type"] == "cash" and row["openingBalance"] == 5000 and row["icon"] == "ruble"

    client.patch(f"/api/accounts/{cash}", json={"icon": "sack"})
    assert api.acct(cash)["icon"] == "sack"

    dup = client.post("/api/accounts", json={"name": "Vault"})
    assert dup.status_code == 409

    bad_type = client.post("/api/accounts", json={"name": "Weird", "type": "crypto"})
    assert bad_type.status_code == 400

    client.patch(f"/api/accounts/{cash}", json={"name": "Wallet", "archived": True})
    row = api.acct(cash)
    assert row["name"] == "Wallet" and row["archived"] is True


def test_account_color_and_custom_image(api: Api, client: TestClient) -> None:
    acc = api.account("Broker", color="#2f6feb")
    assert api.acct(acc)["color"] == "#2f6feb"

    bad = client.patch(f"/api/accounts/{acc}", json={"color": "blue"})
    assert bad.status_code == 400
    assert bad.json()["detail"] == "color must be a #rrggbb hex string"

    img = "data:image/png;base64,iVBORw0KGgo="
    client.patch(f"/api/accounts/{acc}", json={"iconImage": img})
    assert api.acct(acc)["iconImage"] == img

    # empty string clears the custom image back to the glyph
    client.patch(f"/api/accounts/{acc}", json={"iconImage": ""})
    assert api.acct(acc)["iconImage"] is None

    too_big = client.patch(
        f"/api/accounts/{acc}",
        json={"iconImage": "data:image/png;base64," + "A" * 300001},
    )
    assert too_big.status_code == 400
    assert too_big.json()["detail"] == "icon image must be a data URL image under the size limit"

    not_image = client.patch(f"/api/accounts/{acc}", json={"iconImage": "data:text/plain,hi"})
    assert not_image.status_code == 400


def test_reorder_accounts(api: Api, client: TestClient) -> None:
    a = api.account("A")
    b = api.account("B")
    default = api.default_account()
    r = client.post("/api/accounts/reorder", json={"ids": [b, a, default]})
    assert r.status_code == 200
    order = [x["id"] for x in api.snapshot()["accounts"]]
    assert order == [b, a, default]

    bad = client.post("/api/accounts/reorder", json={"ids": [b, a]})
    assert bad.status_code == 400


def test_delete_reassigns_transactions(api: Api, client: TestClient) -> None:
    default = api.default_account()
    cash = api.account("Vault")
    tx = api.tx("2026-03-01T10:00:00", -1000, accountId=cash)

    no_target = client.delete(f"/api/accounts/{cash}")
    assert no_target.status_code == 400

    ok = client.delete(f"/api/accounts/{cash}?reassignTo={default}")
    assert ok.status_code == 200
    assert api.tx_by(tx)["accountId"] == default
    assert cash not in [a["id"] for a in api.snapshot()["accounts"]]

    # the moved row was re-fingerprinted for its new account: importing the
    # same operation into the target account dedups against it
    import app.db as dbmod
    from app.importer import tx_hash

    c = dbmod.connect()
    stored = c.execute("SELECT hash FROM transactions WHERE id=?", (tx,)).fetchone()[0]
    c.close()
    assert stored == tx_hash(default, "2026-03-01T10:00:00", -1000, "")


def test_cannot_delete_last_account(api: Api, client: TestClient) -> None:
    default = api.default_account()
    r = client.delete(f"/api/accounts/{default}")
    assert r.status_code == 400


def test_empty_account_deletes_without_target(api: Api, client: TestClient) -> None:
    acc = api.account("Scratch")
    r = client.delete(f"/api/accounts/{acc}")
    assert r.status_code == 200


def test_transactions_filter_by_account(api: Api, client: TestClient) -> None:
    default = api.default_account()
    cash = api.account("Vault")
    api.tx("2026-03-01T10:00:00", -1000, accountId=default)
    api.tx("2026-03-02T10:00:00", -2000, accountId=cash)
    only_cash = client.get(f"/api/transactions?accountId={cash}").json()
    assert only_cash["total"] == 1 and only_cash["rows"][0]["accountId"] == cash


def test_reconcile_posts_adjustment_for_the_delta(api: Api, client: TestClient) -> None:
    acc = api.account("Vault", openingBalance=10000)
    cat = api.category("Misc", api.group("Stuff"))
    api.tx("2026-03-01T10:00:00", -2500, accountId=acc, categoryId=cat)  # balance now 7500

    r = client.post(f"/api/accounts/{acc}/reconcile", json={"actualBalance": 9000})
    assert r.status_code == 200 and r.json()["delta"] == 1500

    rows = [t for t in api.snapshot()["transactions"] if t["accountId"] == acc]
    adjustment = next(t for t in rows if t["source"] == "adjustment")
    assert adjustment["amount"] == 1500

    # already reconciled -> no further adjustment
    again = client.post(f"/api/accounts/{acc}/reconcile", json={"actualBalance": 9000})
    assert again.json()["delta"] == 0


def test_reconcile_ignores_hidden_transactions(api: Api, client: TestClient) -> None:
    acc = api.account("Vault", openingBalance=10000)
    junk = api.tx("2026-03-01T10:00:00", -2500, accountId=acc)
    client.patch(f"/api/transactions/{junk}", json={"hidden": True})

    # the user sees 10000, so matching reality must post no adjustment
    r = client.post(f"/api/accounts/{acc}/reconcile", json={"actualBalance": 10000})
    assert r.status_code == 200 and r.json()["delta"] == 0


def test_reconcile_skips_rows_the_balance_does_not_count(api: Api, client: TestClient) -> None:
    """
    An uncategorized row that is no transfer is money the ledger has not
    accepted: the account pages leave it out of the balance, so reconciling
    against the bank must not fold it in and post a phantom adjustment.
    """
    acc = api.account("Vault", openingBalance=10000)
    api.tx("2026-03-01T10:00:00", -2500, accountId=acc)

    r = client.post(f"/api/accounts/{acc}/reconcile", json={"actualBalance": 10000})
    assert r.status_code == 200 and r.json()["delta"] == 0


def test_import_targets_account(api: Api, client: TestClient) -> None:
    cash = api.account("Vault")
    rows = api.preview(api.statement)
    client.post("/api/import/commit", json={"accountId": cash, "rows": rows})
    imported = client.get(f"/api/transactions?accountId={cash}").json()
    assert imported["total"] == 2

    bad = client.post("/api/import/commit", json={"accountId": 999, "rows": rows})
    assert bad.status_code == 400


def test_card_tails_stored_normalized_and_validated(api: Api, client: TestClient) -> None:
    acc = api.account("Card", cardTails=["*8181", "8181", "29-47"])
    row = api.acct(acc)
    assert row["cardTails"] == ["8181", "2947"]

    client.patch(f"/api/accounts/{acc}", json={"cardTails": ["*1111"]})
    assert api.acct(acc)["cardTails"] == ["1111"]

    client.patch(f"/api/accounts/{acc}", json={"cardTails": []})
    assert api.acct(acc)["cardTails"] == []

    bad = client.patch(f"/api/accounts/{acc}", json={"cardTails": ["no-digits"]})
    assert bad.status_code == 400
