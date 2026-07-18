from . import db as dbmod


def conn():
    return dbmod.connect()


def serialize_group(r):
    return {"id": r["id"], "name": r["name"], "sort": r["sort"], "kind": r["kind"]}


def serialize_category(r):
    return {
        "id": r["id"],
        "groupId": r["group_id"],
        "name": r["name"],
        "keywords": r["keywords"],
        "sort": r["sort"],
        "archived": bool(r["archived"]),
    }


def serialize_account(r):
    return {
        "id": r["id"],
        "name": r["name"],
        "type": r["type"],
        "icon": r["icon"],
        "color": r["color"],
        "iconImage": r["icon_image"],
        "currency": r["currency"],
        "sort": r["sort"],
        "archived": bool(r["archived"]),
        "openingBalance": r["opening_balance"],
        "openingDate": r["opening_date"],
    }


def serialize_tx(r):
    return {
        "id": r["id"],
        "date": r["date"],
        "amount": r["amount"],
        "description": r["description"],
        "bankCategory": r["bank_category"],
        "mcc": r["mcc"],
        "categoryId": r["category_id"],
        "accountId": r["account_id"],
        "transferId": r["transfer_id"],
        "comment": r["comment"],
        "source": r["source"],
    }


def serialize_budget(r):
    return {
        "categoryId": r["category_id"],
        "year": r["year"],
        "month": r["month"],
        "amount": r["amount"],
    }


def snapshot(c):
    cur = c.cursor()
    return {
        "accounts": [
            serialize_account(r)
            for r in cur.execute(
                "SELECT id, name, type, icon, color, icon_image, currency, sort, archived,"
                " opening_balance, opening_date FROM accounts ORDER BY sort, id"
            )
        ],
        "groups": [
            serialize_group(r)
            for r in cur.execute(
                "SELECT id, name, sort, kind FROM category_groups ORDER BY sort, id"
            )
        ],
        "categories": [
            serialize_category(r)
            for r in cur.execute(
                "SELECT id, group_id, name, keywords, sort, archived FROM categories"
                " ORDER BY sort, id"
            )
        ],
        "transactions": [
            serialize_tx(r)
            for r in cur.execute(
                "SELECT id, date, amount, description, bank_category, mcc, category_id,"
                " account_id, transfer_id, comment, source FROM transactions ORDER BY date, id"
            )
        ],
        "budgets": [
            serialize_budget(r)
            for r in cur.execute(
                "SELECT category_id, year, month, amount FROM budgets"
                " ORDER BY year, month, category_id"
            )
        ],
    }
