import pytest

from app.emails import canonical_email, normalize_email


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("  User@Example.COM ", "user@example.com"),
        ("plain@example.com", "plain@example.com"),
    ],
)
def test_normalize_email(raw, expected):
    assert normalize_email(raw) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        # gmail ignores dots and +tags
        ("anton.ingrish@gmail.com", "antoningrish@gmail.com"),
        ("a.n.t.o.n@gmail.com", "anton@gmail.com"),
        ("Anton.Ingrish+shop@GMail.com", "antoningrish@gmail.com"),
        ("user@googlemail.com", "user@googlemail.com"),
        ("u.s.e.r+x@googlemail.com", "user@googlemail.com"),
        # other domains: +tag stripped, dots kept
        ("user+promo@example.com", "user@example.com"),
        ("a.b@example.com", "a.b@example.com"),
        ("plain@example.com", "plain@example.com"),
        # degenerate local part is left intact, never collapsed to "@domain"
        ("+tag@gmail.com", "+tag@gmail.com"),
        (".@gmail.com", ".@gmail.com"),
        # no @ falls through unchanged (validation happens elsewhere)
        ("not-an-email", "not-an-email"),
    ],
)
def test_canonical_email(raw, expected):
    assert canonical_email(raw) == expected


def test_canonical_email_is_idempotent():
    once = canonical_email("Anton.Ingrish+shop@gmail.com")
    assert canonical_email(once) == once
