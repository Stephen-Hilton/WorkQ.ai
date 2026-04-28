"""Unit tests for the pre-signup whitelist matcher."""

from __future__ import annotations

from handlers.pre_signup import _matches


def test_exact_match() -> None:
    wl = ["alice@example.com"]
    assert _matches("alice@example.com", wl)
    assert _matches("ALICE@EXAMPLE.COM", wl)  # case-insensitive
    assert not _matches("bob@example.com", wl)


def test_domain_wildcard() -> None:
    wl = ["@example.com"]
    assert _matches("alice@example.com", wl)
    assert _matches("bob@example.com", wl)
    assert not _matches("alice@other.com", wl)


def test_mixed() -> None:
    wl = ["alice@example.com", "@trusted.org"]
    assert _matches("alice@example.com", wl)
    assert _matches("anyone@trusted.org", wl)
    assert not _matches("bob@example.com", wl)
    assert not _matches("anyone@untrusted.org", wl)


def test_empty_inputs() -> None:
    assert not _matches("", ["alice@example.com"])
    assert not _matches("alice@example.com", [])
