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


def serialize_tx(r):
    return {
        "id": r["id"],
        "date": r["date"],
        "amount": r["amount"],
        "description": r["description"],
        "bankCategory": r["bank_category"],
        "mcc": r["mcc"],
        "categoryId": r["category_id"],
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
        "groups": [
            serialize_group(r)
            for r in cur.execute("SELECT id, name, sort, kind FROM category_groups ORDER BY sort")
        ],
        "categories": [
            serialize_category(r) for r in cur.execute("SELECT * FROM categories ORDER BY sort")
        ],
        "transactions": [
            serialize_tx(r) for r in cur.execute("SELECT * FROM transactions ORDER BY date")
        ],
        "budgets": [serialize_budget(r) for r in cur.execute("SELECT * FROM budgets")],
    }
