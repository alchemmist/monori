import pathlib
import re
import sys

import pytest
from fastapi import HTTPException

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from app.currencies import CURRENCIES, catalog, is_known, normalize, symbol, validate


def _web_currencies():
    """
    The frontend registry, found by walking up rather than by counting parents:
    mutmut runs this suite from a copy under ``server/mutants/``, where a fixed
    depth points at nothing.
    """
    for parent in pathlib.Path(__file__).resolve().parents:
        candidate = parent / "web" / "src" / "currencies.js"
        if candidate.exists():
            return candidate
    return None


WEB_CURRENCIES = _web_currencies()


def test_normalize_trims_and_upcases():
    assert normalize(" gel ") == "GEL"
    assert normalize(None) == "RUB"
    assert normalize("", "USD") == "USD"
    assert normalize(None, "") == ""


def test_unknown_codes_survive_normalization_but_fail_validation():
    # data written before a code left the registry must still be readable
    assert normalize("xyz") == "XYZ"
    assert not is_known("XYZ")
    with pytest.raises(HTTPException) as e:
        validate("XYZ")
    assert e.value.status_code == 400


def test_validate_returns_the_normalized_code():
    assert validate(" usd ") == "USD"
    assert validate(None) == "RUB"
    assert validate(None, "EUR") == "EUR"


def test_symbol_falls_back_to_the_code():
    assert symbol("RUB") == "₽"
    assert symbol("gel") == "₾"
    assert symbol("XYZ") == "XYZ"


def test_catalog_covers_every_currency():
    entries = catalog()
    assert [e["code"] for e in entries] == list(CURRENCIES)
    assert all(e["minorUnits"] == 2 for e in entries)


@pytest.mark.skipif(WEB_CURRENCIES is None, reason="frontend tree is not next to this checkout")
def test_frontend_registry_lists_the_same_codes():
    """
    The two lists are written twice — once per language — and a code offered on
    one side but rejected on the other would only surface as a 400 in someone's
    account dialog.
    """
    source = WEB_CURRENCIES.read_text()
    codes = re.findall(r'code:\s*"([A-Z]{3})"', source)
    assert codes == list(CURRENCIES)
