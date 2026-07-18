import pathlib
import sys

import pytest
from fastapi import HTTPException

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
from app.routers.accounts import MAX_ICON_IMAGE, _validate_color, _validate_icon_image


def test_validate_color_accepts_six_digit_hex():
    _validate_color("#5b6472")
    _validate_color("#FFFFFF")


@pytest.mark.parametrize("bad", ["5b6472", "#5b647", "#5b64722", "#zzzzzz", "", "#5b 472"])
def test_validate_color_rejects_non_hex(bad):
    with pytest.raises(HTTPException) as e:
        _validate_color(bad)
    assert e.value.status_code == 400


def test_validate_icon_image_allows_empty():
    # empty / None means "no custom image" and must pass silently
    _validate_icon_image("")
    _validate_icon_image(None)


def test_validate_icon_image_allows_data_url_at_the_size_cap():
    image = "data:image/png;base64," + "A" * (MAX_ICON_IMAGE - len("data:image/png;base64,"))
    assert len(image) == MAX_ICON_IMAGE
    _validate_icon_image(image)  # exactly at the cap is allowed (guard is strictly >)


def test_validate_icon_image_rejects_non_image_data():
    with pytest.raises(HTTPException) as e:
        _validate_icon_image("data:text/plain;base64,AAAA")
    assert e.value.status_code == 400


def test_validate_icon_image_rejects_oversize_image():
    image = "data:image/png;base64," + "A" * MAX_ICON_IMAGE
    with pytest.raises(HTTPException):
        _validate_icon_image(image)
