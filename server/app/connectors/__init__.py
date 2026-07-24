"""
Pluggable bank connectors.

A connector knows how to pull transactions from one bank via one mechanism
(browser automation, a file drop, an API) and return them in the parsed-row
shape the ingestion pipeline expects. Real connectors register themselves on
import; importing this package makes them discoverable through the registry in
:mod:`app.connectors.base`.
"""

from . import base, tbank_playwright  # noqa: F401
