"""Unit tests for POST /id."""

from __future__ import annotations

import json
import os
from unittest.mock import patch

# Set required env before importing handlers.
os.environ.setdefault("DDB_TABLE", "test-table")


def _event(body: dict, email: str = "alice@example.com") -> dict:
    return {
        "body": json.dumps(body),
        "requestContext": {"authorizer": {"claims": {"email": email}}},
    }


def test_post_generates_uuid_and_sets_creator() -> None:
    from handlers import post_id

    captured: dict = {}

    def fake_put_item(item: dict) -> None:
        captured["item"] = item

    with patch("handlers.post_id.ddb.put_item", side_effect=fake_put_item):
        resp = post_id.handler(_event({"request": "do the thing"}), None)

    assert resp["statusCode"] == 201
    item = captured["item"]
    assert item["reqid"]  # generated
    assert item["reqcreator"] == "alice@example.com"
    assert item["request"] == "do the thing"
    assert item["reqarea"] == "General"
    assert item["reqstatus"] == "pending review"
    assert len(item["timelog"]) == 1
    assert item["timelog"][0]["status"] == "pending review"


def test_post_ignores_client_supplied_reqid_and_creator() -> None:
    from handlers import post_id

    captured: dict = {}

    def fake_put_item(item: dict) -> None:
        captured["item"] = item

    body = {
        "reqid": "client-supplied-bad",
        "reqcreator": "evil@attacker.com",
        "request": "x",
    }
    with patch("handlers.post_id.ddb.put_item", side_effect=fake_put_item):
        post_id.handler(_event(body, email="alice@example.com"), None)

    item = captured["item"]
    assert item["reqid"] != "client-supplied-bad"
    assert item["reqcreator"] == "alice@example.com"


def test_post_falls_back_to_service_user_when_no_jwt() -> None:
    from handlers import post_id

    captured: dict = {}

    def fake_put_item(item: dict) -> None:
        captured["item"] = item

    event = {"body": json.dumps({"request": "x"})}  # no requestContext.claims
    with patch("handlers.post_id.ddb.put_item", side_effect=fake_put_item):
        post_id.handler(event, None)

    assert captured["item"]["reqcreator"].endswith("@requestqueue.internal")
