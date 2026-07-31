"""
A deterministic in-memory connector for exercising the sync path in tests.

It reproduces the two-phase login: the first sync of a fresh connection raises
:class:`SmsRequired`; supplying the code ``0000`` via :meth:`resume_sync`
"authenticates" and returns rows. Once a session is cached, later syncs return
rows directly with no OTP. It is registered only when this module is imported
(tests do so explicitly) and is hidden from the bank picker.
"""

from typing import cast

from .base import Connector, ConnectorError, SmsRequired, SyncResult, SyncRow, register

FIXTURE_ROWS: list[SyncRow] = [
    {
        "date": "2026-02-01T09:00:00",
        "amount": -50000,
        "description": "Lenta",
        "bank_category": "Supermarkets",
        "mcc": "5411",
        "card": "*1111",
    },
    {
        "date": "2026-02-02T12:30:00",
        "amount": 250000,
        "description": "Salary",
        "bank_category": "Income",
        "mcc": "",
        "card": "*1111",
    },
]


def _rows(account_ref: str | None = None) -> list[SyncRow]:
    """
    A real bank scopes the feed to the requested account; the fixture mimics
    that by stamping the ref into the description, so two accounts on one
    connection deliver distinct operations rather than one feed twice.
    """
    rows = cast("list[SyncRow]", [dict(r) for r in FIXTURE_ROWS])
    if account_ref:
        for r in rows:
            r["description"] = f"{r['description']} {account_ref}"
    return rows


@register
class FakeConnector(Connector):
    bank = "fake"
    kind = "fake"
    hidden = True

    def sync(self, since: str | None = None) -> SyncResult:
        if not self.credentials.get("phone"):
            raise ConnectorError("missing phone")
        session = self.session
        if session and session.get("token"):
            return SyncResult(_rows(self.account_ref), session=session)
        self._pending = True
        raise SmsRequired("code sent")

    def resume_sync(self, code: str) -> SyncResult:
        if not getattr(self, "_pending", False):
            raise ConnectorError("no login in progress")
        if code != "0000":
            raise ConnectorError("invalid code")
        return SyncResult(_rows(self.account_ref), session={"token": "ok"})
