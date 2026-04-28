"""DynamoDB client + helpers for the WorkQ requests table."""

from __future__ import annotations

import os
from functools import lru_cache
from typing import Any

import boto3
from botocore.exceptions import ClientError


@lru_cache(maxsize=1)
def table() -> Any:
    """Cached DDB Table resource. Re-used across warm Lambda invocations."""
    name = os.environ["DDB_TABLE"]
    return boto3.resource("dynamodb").Table(name)


def get_item(reqid: str) -> dict[str, Any] | None:
    resp = table().get_item(Key={"reqid": reqid})
    return resp.get("Item")


def put_item(item: dict[str, Any]) -> None:
    """Create-only put (fails on existing reqid)."""
    table().put_item(
        Item=item,
        ConditionExpression="attribute_not_exists(reqid)",
    )


def delete_item(reqid: str) -> None:
    table().delete_item(Key={"reqid": reqid})


def scan_all() -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    kwargs: dict[str, Any] = {}
    while True:
        resp = table().scan(**kwargs)
        items.extend(resp.get("Items", []))
        if "LastEvaluatedKey" not in resp:
            break
        kwargs["ExclusiveStartKey"] = resp["LastEvaluatedKey"]
    return items


def scan_by_status(statuses: list[str]) -> list[dict[str, Any]]:
    """Scan with a status filter. `statuses` is OR-ed."""
    items: list[dict[str, Any]] = []
    expr_attr_values = {f":s{i}": s for i, s in enumerate(statuses)}
    filter_expr = " OR ".join(f"reqstatus = :s{i}" for i in range(len(statuses)))
    kwargs: dict[str, Any] = {
        "FilterExpression": filter_expr,
        "ExpressionAttributeValues": expr_attr_values,
    }
    while True:
        resp = table().scan(**kwargs)
        items.extend(resp.get("Items", []))
        if "LastEvaluatedKey" not in resp:
            break
        kwargs["ExclusiveStartKey"] = resp["LastEvaluatedKey"]
    return items


class ConcurrencyConflict(Exception):
    """Raised when a PUT's optimistic-concurrency check fails."""


def update_item(
    reqid: str,
    fields: dict[str, Any],
    new_timelog_entry: dict[str, Any],
    expected_timelog_len: int | None,
) -> dict[str, Any]:
    """Apply a partial update with optimistic concurrency.

    `fields` is the set of fields to overwrite (excluding `reqid`, `reqcreator`,
    and `timelog` which are managed here).

    `new_timelog_entry` is the entry to append to `timelog`.

    `expected_timelog_len` (if not None) is enforced via DDB
    ConditionExpression. On mismatch, raises ConcurrencyConflict.

    Returns the updated item.
    """
    set_parts: list[str] = []
    expr_values: dict[str, Any] = {}
    expr_names: dict[str, str] = {}

    for k, v in fields.items():
        if k in ("reqid", "reqcreator", "timelog"):
            continue
        if v is None:
            continue
        placeholder = f":v_{k}"
        name_placeholder = f"#k_{k}"
        set_parts.append(f"{name_placeholder} = {placeholder}")
        expr_values[placeholder] = v
        expr_names[name_placeholder] = k

    # Always append a timelog entry on update.
    expr_values[":new_log"] = [new_timelog_entry]
    expr_values[":empty_list"] = []
    set_parts.append(
        "timelog = list_append(if_not_exists(timelog, :empty_list), :new_log)"
    )

    update_expression = "SET " + ", ".join(set_parts)

    condition: str | None = None
    if expected_timelog_len is not None:
        expr_values[":expected_len"] = expected_timelog_len
        condition = "size(timelog) = :expected_len"

    kwargs: dict[str, Any] = {
        "Key": {"reqid": reqid},
        "UpdateExpression": update_expression,
        "ExpressionAttributeValues": expr_values,
        "ReturnValues": "ALL_NEW",
    }
    if expr_names:
        kwargs["ExpressionAttributeNames"] = expr_names
    if condition is not None:
        kwargs["ConditionExpression"] = condition

    try:
        resp = table().update_item(**kwargs)
    except ClientError as e:
        if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
            raise ConcurrencyConflict(reqid) from e
        raise

    return resp["Attributes"]
