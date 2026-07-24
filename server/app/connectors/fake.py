"""
A deterministic in-memory connector for exercising the sync path in tests.

It reproduces the two-phase login: the first sync of a fresh connection raises
:class:`SmsRequired`; supplying the code ``0000`` via :meth:`resume_sync`
"authenticates" and returns rows. Once a session is cached, later syncs return
rows directly with no OTP. It is registered only when this module is imported
(tests do so explicitly) and is hidden from the bank picker.
"""

from ..importer import tx_hash
from .base import Connector, ConnectorError, SmsRequired, SyncResult, register

FIXTURE_ROWS = [
    {
        "date": "2026-02-01T09:00:00",
        "amount": -50000,
        "description": "Lenta",
        "bank_category": "Supermarkets",
        "mcc": "5411",
    },
    {
        "date": "2026-02-02T12:30:00",
        "amount": 250000,
        "description": "Salary",
        "bank_category": "Income",
        "mcc": "",
    },
]


def _rows():
    out = []
    for r in FIXTURE_ROWS:
        row = dict(r)
        row["hash"] = tx_hash(row["date"], row["amount"], row["description"])
        out.append(row)
    return out


@register
class FakeConnector(Connector):
    bank = "fake"
    kind = "fake"
    hidden = True

    def sync(self, since=None):
        if not self.credentials.get("phone"):
            raise ConnectorError("missing phone")
        if self.session and self.session.get("token"):
            return SyncResult(_rows(), session=self.session)
        self._pending = True
        raise SmsRequired("code sent")

    def resume_sync(self, code):
        if not getattr(self, "_pending", False):
            raise ConnectorError("no login in progress")
        if code != "0000":
            raise ConnectorError("invalid code")
        return SyncResult(_rows(), session={"token": "ok"})
