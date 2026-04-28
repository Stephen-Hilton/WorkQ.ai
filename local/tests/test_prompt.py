"""Unit tests for prompt assembly."""

from __future__ import annotations

from build.prompt import PromptParts


def test_general_area_auto_injected() -> None:
    p = PromptParts({"all": {}, "status": {}, "areas": {"webapp": {"pre": "x", "post": "y"}}})
    areas = p.areas()
    assert "General" in areas
    assert "webapp" in areas


def test_render_assembles_in_order() -> None:
    p = PromptParts(
        {
            "all": {"pre": "ALL_PRE", "post": "ALL_POST"},
            "status": {
                "build": {"pre": "BUILD_PRE", "post": "BUILD_POST"},
            },
            "areas": {
                "webapp": {"pre": "WEB_PRE", "post": "WEB_POST"},
            },
        }
    )
    out = p.render(reqstatus="queued for build", reqarea="webapp", request="DO THIS")
    # Pre order
    assert out.index("ALL_PRE") < out.index("BUILD_PRE") < out.index("WEB_PRE")
    # Body
    assert "DO THIS" in out
    # Post order
    assert out.index("ALL_POST") < out.index("BUILD_POST") < out.index("WEB_POST")
    # Body sits between pre and post
    assert out.index("WEB_PRE") < out.index("DO THIS") < out.index("ALL_POST")


def test_render_includes_prior_response() -> None:
    p = PromptParts({"all": {}, "status": {}, "areas": {}})
    out = p.render(
        reqstatus="queued for build",
        reqarea="General",
        request="REQ",
        prior_response="PRIOR",
    )
    assert "REQ" in out
    assert "Previous AI Responses" in out
    assert "PRIOR" in out


def test_render_no_status_block_for_unknown_status() -> None:
    p = PromptParts({"all": {}, "status": {"build": {"pre": "X"}}, "areas": {}})
    out = p.render(reqstatus="building", reqarea="General", request="r")
    # "building" maps to "build", so should include X
    assert "X" in out
    out2 = p.render(reqstatus="weird-status", reqarea="General", request="r")
    assert "X" not in out2


def test_render_falls_back_to_general_area_for_unknown_area() -> None:
    p = PromptParts({"all": {}, "status": {}, "areas": {"General": {"pre": "G_PRE"}}})
    out = p.render(reqstatus="queued for build", reqarea="nonexistent", request="r")
    assert "G_PRE" in out
