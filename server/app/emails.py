"""
Email normalisation and canonicalisation.

``normalize`` yields the display form (trimmed, lower-cased). ``canonical``
collapses a real mailbox's aliases to a single key so one inbox cannot own
several accounts: sub-addressing (a ``+tag`` suffix on the local part) is dropped
for every domain, and dots in the local part are dropped for Gmail, which ignores
them. Both fall back to leaving the local part untouched if stripping would empty
it, so a degenerate address never canonicalises to a bare ``@domain``.
"""

GMAIL_DOMAINS = {"gmail.com", "googlemail.com"}


def normalize_email(email):
    return email.strip().lower()


def canonical_email(email):
    email = normalize_email(email)
    local, sep, domain = email.partition("@")
    if not sep:
        return email
    base = local.split("+", 1)[0]
    if domain in GMAIL_DOMAINS:
        base = base.replace(".", "")
    return f"{base or local}@{domain}"
