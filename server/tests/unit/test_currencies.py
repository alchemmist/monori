import pathlib
import re

import pytest
from fastapi import HTTPException

from monori.server.app.currencies import CURRENCIES, catalog, is_known, normalize, symbol, validate


def _web_currencies() -> pathlib.Path | None:
    """Locate the frontend registry in the checkout or mutation workspace."""
    for parent in pathlib.Path(__file__).resolve().parents:
        candidate = parent / "web" / "src" / "currencies.ts"
        if candidate.exists():
            return candidate
    return None


WEB_CURRENCIES = _web_currencies()


def test_normalize_trims_and_upcases() -> None:
    assert normalize(" gel ") == "GEL"
    assert normalize(None) == "RUB"
    assert normalize("", "USD") == "USD"
    assert normalize(None, "") == ""


def test_unknown_codes_survive_normalization_but_fail_validation() -> None:

    assert normalize("xyz") == "XYZ"
    assert not is_known("XYZ")

    assert not is_known("")
    assert not is_known(None)
    assert is_known(" rub ")
    with pytest.raises(HTTPException) as e:
        validate("XYZ")
    assert e.value.status_code == 400


def test_validate_returns_the_normalized_code() -> None:
    assert validate(" usd ") == "USD"
    assert validate(None) == "RUB"
    assert validate(None, "EUR") == "EUR"


def test_symbol_falls_back_to_the_code() -> None:
    assert symbol("RUB") == "₽"
    assert symbol("gel") == "₾"
    assert symbol("XYZ") == "XYZ"

    assert symbol("") == ""
    assert symbol(None) == ""


def test_catalog_covers_every_currency() -> None:
    entries = catalog()
    assert [e["code"] for e in entries] == list(CURRENCIES)
    assert all(e["minorUnits"] == 2 for e in entries)

    assert all(set(e) == {"code", "name", "symbol", "minorUnits"} for e in entries)
    assert entries[0] == {"code": "RUB", "name": "Russian ruble", "symbol": "₽", "minorUnits": 2}


@pytest.mark.skipif(WEB_CURRENCIES is None, reason="frontend tree is not next to this checkout")
def test_frontend_registry_lists_the_same_codes() -> None:
    """Keep the frontend and backend currency catalogs aligned."""
    assert WEB_CURRENCIES is not None
    source = WEB_CURRENCIES.read_text()
    codes = re.findall(r'code:\s*"([A-Z]{3})"', source)
    assert codes == list(CURRENCIES)
