from __future__ import annotations

from typing import Any

API_BASE_PROPERTY = {"type": "string", "description": "Optional Pony Mail API base URL"}
CACHE_DIR_PROPERTY = {
    "type": "string",
    "description": "Optional local cache directory for Incubator general mail summaries",
}
QUERY_PROPERTY = {"type": "string", "description": "Case-insensitive search query"}
TIMESPAN_PROPERTY = {
    "type": "string",
    "description": "Pony Mail timespan, for example lte=1M, lte=12M, or 2026-04",
}
LIMIT_PROPERTY = {"type": "integer", "description": "Optional maximum number of results"}
MESSAGE_ID_PROPERTY = {
    "type": "string",
    "description": "Pony Mail id, mid, or Message-ID header value",
}
BOOLEAN_PROPERTY = {"type": "boolean", "description": "Optional boolean flag"}
MONTH_PROPERTY = {"type": "string", "description": "Month in YYYY-MM format"}
START_MONTH_PROPERTY = {"type": "string", "description": "Start month in YYYY-MM format"}
END_MONTH_PROPERTY = {"type": "string", "description": "End month in YYYY-MM format"}
HEADER_PROPERTY = {"type": "string", "description": "Optional Pony Mail mbox header filter"}


def input_schema(
    properties: dict[str, Any], *, required: list[str] | None = None
) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": properties,
        "required": required or [],
        "additionalProperties": False,
    }


def tool_definition(
    *,
    description: str,
    handler: Any,
    properties: dict[str, Any],
    required: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "description": description,
        "inputSchema": input_schema(properties, required=required),
        "handler": handler,
    }


def live_query_properties() -> dict[str, Any]:
    return {
        "api_base": API_BASE_PROPERTY,
        "timespan": TIMESPAN_PROPERTY,
        "query": QUERY_PROPERTY,
        "limit": LIMIT_PROPERTY,
    }


def email_properties() -> dict[str, Any]:
    return {
        "api_base": API_BASE_PROPERTY,
        "message_id": MESSAGE_ID_PROPERTY,
    }


def cache_properties() -> dict[str, Any]:
    return {
        **live_query_properties(),
        "cache_dir": CACHE_DIR_PROPERTY,
    }


def mbox_cache_properties() -> dict[str, Any]:
    return {
        "api_base": API_BASE_PROPERTY,
        "cache_dir": CACHE_DIR_PROPERTY,
        "month": MONTH_PROPERTY,
        "header_from": HEADER_PROPERTY,
        "header_subject": HEADER_PROPERTY,
        "header_body": HEADER_PROPERTY,
    }


def mbox_range_cache_properties() -> dict[str, Any]:
    return {
        "api_base": API_BASE_PROPERTY,
        "cache_dir": CACHE_DIR_PROPERTY,
        "start_month": START_MONTH_PROPERTY,
        "end_month": END_MONTH_PROPERTY,
        "header_from": HEADER_PROPERTY,
        "header_subject": HEADER_PROPERTY,
        "header_body": HEADER_PROPERTY,
    }


def cached_mbox_properties() -> dict[str, Any]:
    return {
        "cache_dir": CACHE_DIR_PROPERTY,
    }


def cached_list_properties() -> dict[str, Any]:
    return {
        "cache_dir": CACHE_DIR_PROPERTY,
        "query": QUERY_PROPERTY,
        "limit": LIMIT_PROPERTY,
    }


def cached_email_properties() -> dict[str, Any]:
    return {
        "cache_dir": CACHE_DIR_PROPERTY,
        "message_id": MESSAGE_ID_PROPERTY,
    }
