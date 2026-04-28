"""Unit tests for the status-fence parser."""

from __future__ import annotations

from build.claude_runner import parse_fence


def test_no_fence_returns_none() -> None:
    assert parse_fence("# All done!\n\nNo issues here.") is None


def test_pending_review_fence() -> None:
    text = "# Question\n\nWhat color?\n\n<!-- workq:status=pending_review -->"
    assert parse_fence(text) == "pending_review"


def test_failed_fence() -> None:
    text = "Could not find the file.\n<!-- workq:status=failed -->\n"
    assert parse_fence(text) == "failed"


def test_complete_fence_explicit() -> None:
    text = "Done.\n<!-- workq:status=complete -->"
    assert parse_fence(text) == "complete"


def test_unknown_fence_value_ignored() -> None:
    assert parse_fence("done\n<!-- workq:status=funky -->") is None


def test_last_fence_wins() -> None:
    """If claude writes multiple fences, the last one is canonical."""
    text = "<!-- workq:status=failed -->\n\nactually I fixed it\n<!-- workq:status=complete -->"
    assert parse_fence(text) == "complete"


def test_fence_in_middle_of_long_text_still_found() -> None:
    """Only the last 2KB of output is scanned, but a fence on the last line of
    a verbose response should still be picked up."""
    long = "lorem ipsum " * 500
    text = f"{long}\n<!-- workq:status=failed -->"
    assert parse_fence(text) == "failed"


def test_fence_in_first_2kb_of_huge_text_not_picked_up() -> None:
    """A fence that's swamped by very long output past the 2KB tail isn't seen."""
    huge = "x" * 5000
    text = f"<!-- workq:status=failed -->\n{huge}"
    assert parse_fence(text) is None
