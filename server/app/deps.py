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
        "connectionId": r["connection_id"],
        "bankRef": r["bank_ref"],
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


def serialize_user(r):
    """A user, without the password hash."""
    return {"id": r["id"], "email": r["email"], "createdAt": r["created_at"]}


def serialize_connection(r):
    """A bank connection, without any secret material (credentials/session)."""
    return {
        "id": r["id"],
        "bank": r["bank"],
        "kind": r["kind"],
        "status": r["status"],
        "lastSync": r["last_sync"],
        "lastError": r["last_error"],
        "hasCredentials": r["credentials_encrypted"] is not None,
        "createdAt": r["created_at"],
        "updatedAt": r["updated_at"],
    }


def serialize_budget(r):
    return {
        "categoryId": r["category_id"],
        "year": r["year"],
        "month": r["month"],
        "amount": r["amount"],
    }


def snapshot(c, user_id):
    cur = c.cursor()
    uid = (user_id,)
    return {
        "accounts": [
            serialize_account(r)
            for r in cur.execute(
                "SELECT id, name, type, icon, color, icon_image, currency, sort, archived,"
                " opening_balance, opening_date, connection_id, bank_ref"
                " FROM accounts WHERE user_id=? ORDER BY sort, id",
                uid,
            )
        ],
        "groups": [
            serialize_group(r)
            for r in cur.execute(
                "SELECT id, name, sort, kind FROM category_groups WHERE user_id=?"
                " ORDER BY sort, id",
                uid,
            )
        ],
        "categories": [
            serialize_category(r)
            for r in cur.execute(
                "SELECT c.id, c.group_id, c.name, c.keywords, c.sort, c.archived"
                " FROM categories c JOIN category_groups g ON g.id = c.group_id"
                " WHERE g.user_id=? ORDER BY c.sort, c.id",
                uid,
            )
        ],
        "transactions": [
            serialize_tx(r)
            for r in cur.execute(
                "SELECT t.id, t.date, t.amount, t.description, t.bank_category, t.mcc,"
                " t.category_id, t.account_id, t.transfer_id, t.comment, t.source"
                " FROM transactions t JOIN accounts a ON a.id = t.account_id"
                " WHERE a.user_id=? ORDER BY t.date, t.id",
                uid,
            )
        ],
        "budgets": [
            serialize_budget(r)
            for r in cur.execute(
                "SELECT b.category_id, b.year, b.month, b.amount FROM budgets b"
                " JOIN categories c ON c.id = b.category_id"
                " JOIN category_groups g ON g.id = c.group_id"
                " WHERE g.user_id=? ORDER BY b.year, b.month, b.category_id",
                uid,
            )
        ],
        "connections": [
            serialize_connection(r)
            for r in cur.execute(
                "SELECT bc.id, bc.bank, bc.kind, bc.status, bc.last_sync,"
                " bc.last_error, bc.credentials_encrypted, bc.created_at, bc.updated_at"
                " FROM bank_connections bc WHERE bc.user_id=? ORDER BY bc.id",
                uid,
            )
        ],
    }
