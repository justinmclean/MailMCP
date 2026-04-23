from __future__ import annotations

from typing import Any

from apache_incubator_mail_mcp import schemas
from apache_incubator_mail_mcp.client import (
    DEFAULT_API_BASE,
    DEFAULT_CACHE_DIR,
    DEFAULT_SEARCH_TIMESPAN,
    DEFAULT_TIMESPAN,
    cache_mail_stats,
    cache_mbox,
    cache_mbox_range,
    fetch_email,
    fetch_mail_stats,
    find_release_result_threads as client_find_release_result_threads,
    find_release_vote_threads as client_find_release_vote_threads,
    find_cached_mail,
    list_cached_mboxes,
    load_cached_mail,
    podling_release_vote_history as client_podling_release_vote_history,
    summarize_release_vote_thread as client_summarize_release_vote_thread,
)

_CONFIGURED_API_BASE: str | None = None
_CONFIGURED_CACHE_DIR: str | None = None


def configure_defaults(api_base: str | None = None, cache_dir: str | None = None) -> None:
    global _CONFIGURED_API_BASE, _CONFIGURED_CACHE_DIR
    if api_base:
        _CONFIGURED_API_BASE = api_base
    if cache_dir:
        _CONFIGURED_CACHE_DIR = cache_dir


def require_non_empty_string(value: Any, key: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"'{key}' must be a string")
    stripped = value.strip()
    if not stripped:
        raise ValueError(f"'{key}' must be a non-empty string")
    return stripped


def optional_string(value: Any, key: str) -> str | None:
    if value is None:
        return None
    return require_non_empty_string(value, key)


def require_limit(value: Any) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError("'limit' must be an integer")
    if value <= 0:
        raise ValueError("'limit' must be greater than 0")
    return value


def resolve_api_base(value: str | None = None) -> str:
    return optional_string(value, "api_base") or _CONFIGURED_API_BASE or DEFAULT_API_BASE


def resolve_cache_dir(value: str | None = None) -> str:
    return optional_string(value, "cache_dir") or _CONFIGURED_CACHE_DIR or DEFAULT_CACHE_DIR


def resolve_timespan(value: str | None = None, default: str = DEFAULT_TIMESPAN) -> str:
    return optional_string(value, "timespan") or default


def incubator_general_mail_overview(
    api_base: str | None = None,
    timespan: str | None = None,
    query: str | None = None,
    limit: int = 25,
) -> dict[str, Any]:
    """Return a high-level summary of Incubator general list mail."""
    resolved_limit = require_limit(limit)
    stats = fetch_mail_stats(
        api_base=resolve_api_base(api_base),
        timespan=resolve_timespan(timespan),
        query=optional_string(query, "query"),
        limit=resolved_limit,
    )
    return {key: value for key, value in stats.items() if key != "emails"} | {
        "sample": stats["emails"],
    }


def recent_incubator_general_mail(
    api_base: str | None = None,
    timespan: str | None = None,
    query: str | None = None,
    limit: int = 20,
) -> dict[str, Any]:
    """Return recent Incubator general list message summaries."""
    resolved_limit = require_limit(limit)
    return fetch_mail_stats(
        api_base=resolve_api_base(api_base),
        timespan=resolve_timespan(timespan),
        query=optional_string(query, "query"),
        limit=resolved_limit,
    )


def search_incubator_general_mail(
    query: str,
    api_base: str | None = None,
    timespan: str | None = None,
    limit: int = 20,
) -> dict[str, Any]:
    """Search the Incubator general mailing list."""
    resolved_limit = require_limit(limit)
    resolved_query = require_non_empty_string(query, "query")
    return fetch_mail_stats(
        api_base=resolve_api_base(api_base),
        timespan=resolve_timespan(timespan, DEFAULT_SEARCH_TIMESPAN),
        query=resolved_query,
        limit=resolved_limit,
    )


def get_incubator_general_email(message_id: str, api_base: str | None = None) -> dict[str, Any]:
    """Fetch one full Incubator general list email."""
    return fetch_email(
        api_base=resolve_api_base(api_base),
        message_id=require_non_empty_string(message_id, "message_id"),
    )


def cache_incubator_general_mail(
    api_base: str | None = None,
    cache_dir: str | None = None,
    timespan: str | None = None,
    query: str | None = None,
    limit: int = 100,
) -> dict[str, Any]:
    """Cache Incubator general list message summaries locally."""
    return cache_mail_stats(
        api_base=resolve_api_base(api_base),
        cache_dir=resolve_cache_dir(cache_dir),
        timespan=resolve_timespan(timespan),
        query=optional_string(query, "query"),
        limit=require_limit(limit),
    )


def list_cached_incubator_general_mail(
    cache_dir: str | None = None,
    query: str | None = None,
    limit: int = 50,
) -> dict[str, Any]:
    """List cached Incubator general list message summaries."""
    return load_cached_mail(
        cache_dir=resolve_cache_dir(cache_dir),
        query=optional_string(query, "query"),
        limit=require_limit(limit),
    )


def get_cached_incubator_general_email(
    message_id: str,
    cache_dir: str | None = None,
) -> dict[str, Any]:
    """Return one cached Incubator general list message summary."""
    return find_cached_mail(
        cache_dir=resolve_cache_dir(cache_dir),
        message_id=require_non_empty_string(message_id, "message_id"),
    )


def cache_incubator_general_mbox(
    month: str,
    api_base: str | None = None,
    cache_dir: str | None = None,
    header_from: str | None = None,
    header_subject: str | None = None,
    header_body: str | None = None,
) -> dict[str, Any]:
    """Download and cache one monthly mbox for the Incubator general list."""
    return cache_mbox(
        api_base=resolve_api_base(api_base),
        cache_dir=resolve_cache_dir(cache_dir),
        month=require_non_empty_string(month, "month"),
        header_from=optional_string(header_from, "header_from"),
        header_subject=optional_string(header_subject, "header_subject"),
        header_body=optional_string(header_body, "header_body"),
    )


def cache_incubator_general_mboxes(
    start_month: str,
    end_month: str,
    api_base: str | None = None,
    cache_dir: str | None = None,
    header_from: str | None = None,
    header_subject: str | None = None,
    header_body: str | None = None,
) -> dict[str, Any]:
    """Download and cache a range of monthly mboxes for the Incubator general list."""
    return cache_mbox_range(
        api_base=resolve_api_base(api_base),
        cache_dir=resolve_cache_dir(cache_dir),
        start_month=require_non_empty_string(start_month, "start_month"),
        end_month=require_non_empty_string(end_month, "end_month"),
        header_from=optional_string(header_from, "header_from"),
        header_subject=optional_string(header_subject, "header_subject"),
        header_body=optional_string(header_body, "header_body"),
    )


def list_cached_incubator_general_mboxes(cache_dir: str | None = None) -> dict[str, Any]:
    """List cached monthly mbox files for the Incubator general list."""
    return list_cached_mboxes(cache_dir=resolve_cache_dir(cache_dir))


def find_release_vote_threads(
    api_base: str | None = None,
    timespan: str | None = None,
    podling: str | None = None,
    query: str | None = None,
    limit: int = 20,
) -> dict[str, Any]:
    """Find likely Incubator release vote threads."""
    return client_find_release_vote_threads(
        api_base=resolve_api_base(api_base),
        timespan=resolve_timespan(timespan, DEFAULT_SEARCH_TIMESPAN),
        podling=optional_string(podling, "podling"),
        query=optional_string(query, "query"),
        limit=require_limit(limit),
    )


def find_release_result_threads(
    api_base: str | None = None,
    timespan: str | None = None,
    podling: str | None = None,
    query: str | None = None,
    limit: int = 20,
) -> dict[str, Any]:
    """Find likely Incubator release vote result threads."""
    return client_find_release_result_threads(
        api_base=resolve_api_base(api_base),
        timespan=resolve_timespan(timespan, DEFAULT_SEARCH_TIMESPAN),
        podling=optional_string(podling, "podling"),
        query=optional_string(query, "query"),
        limit=require_limit(limit),
    )


def summarize_release_vote_thread(
    message_id: str,
    api_base: str | None = None,
    timespan: str | None = None,
    limit: int = 50,
) -> dict[str, Any]:
    """Summarize likely votes and results in one Incubator release vote thread."""
    return client_summarize_release_vote_thread(
        api_base=resolve_api_base(api_base),
        timespan=resolve_timespan(timespan, DEFAULT_SEARCH_TIMESPAN),
        message_id=require_non_empty_string(message_id, "message_id"),
        limit=require_limit(limit),
    )


def podling_release_vote_history(
    podling: str,
    api_base: str | None = None,
    timespan: str | None = None,
    limit: int = 20,
) -> dict[str, Any]:
    """Return likely release vote and result history for one podling."""
    return client_podling_release_vote_history(
        api_base=resolve_api_base(api_base),
        timespan=resolve_timespan(timespan, DEFAULT_SEARCH_TIMESPAN),
        podling=require_non_empty_string(podling, "podling"),
        limit=require_limit(limit),
    )


TOOLS: dict[str, dict[str, Any]] = {
    "incubator_general_mail_overview": schemas.tool_definition(
        description="Return a high-level summary of Incubator general mailing list activity.",
        handler=incubator_general_mail_overview,
        properties=schemas.live_query_properties(),
    ),
    "recent_incubator_general_mail": schemas.tool_definition(
        description="Return recent message summaries from general@incubator.apache.org.",
        handler=recent_incubator_general_mail,
        properties=schemas.live_query_properties(),
    ),
    "search_incubator_general_mail": schemas.tool_definition(
        description="Search general@incubator.apache.org message summaries.",
        handler=search_incubator_general_mail,
        properties=schemas.live_query_properties(),
        required=["query"],
    ),
    "get_incubator_general_email": schemas.tool_definition(
        description="Fetch one full general@incubator.apache.org email by Pony Mail id or Message-ID.",
        handler=get_incubator_general_email,
        properties=schemas.email_properties(),
        required=["message_id"],
    ),
    "cache_incubator_general_mail": schemas.tool_definition(
        description="Cache general@incubator.apache.org message summaries locally.",
        handler=cache_incubator_general_mail,
        properties=schemas.cache_properties(),
    ),
    "list_cached_incubator_general_mail": schemas.tool_definition(
        description="List cached general@incubator.apache.org message summaries.",
        handler=list_cached_incubator_general_mail,
        properties=schemas.cached_list_properties(),
    ),
    "get_cached_incubator_general_email": schemas.tool_definition(
        description="Return one cached general@incubator.apache.org message summary.",
        handler=get_cached_incubator_general_email,
        properties=schemas.cached_email_properties(),
        required=["message_id"],
    ),
    "cache_incubator_general_mbox": schemas.tool_definition(
        description="Download and cache one monthly general@incubator.apache.org mbox file.",
        handler=cache_incubator_general_mbox,
        properties=schemas.mbox_cache_properties(),
        required=["month"],
    ),
    "cache_incubator_general_mboxes": schemas.tool_definition(
        description="Download and cache a range of monthly general@incubator.apache.org mbox files.",
        handler=cache_incubator_general_mboxes,
        properties=schemas.mbox_range_cache_properties(),
        required=["start_month", "end_month"],
    ),
    "list_cached_incubator_general_mboxes": schemas.tool_definition(
        description="List cached monthly general@incubator.apache.org mbox files.",
        handler=list_cached_incubator_general_mboxes,
        properties=schemas.cached_mbox_properties(),
    ),
    "find_release_vote_threads": schemas.tool_definition(
        description="Find likely Incubator release vote threads on general@incubator.apache.org.",
        handler=find_release_vote_threads,
        properties=schemas.release_thread_search_properties(),
    ),
    "find_release_result_threads": schemas.tool_definition(
        description="Find likely Incubator release vote result threads on general@incubator.apache.org.",
        handler=find_release_result_threads,
        properties=schemas.release_thread_search_properties(),
    ),
    "summarize_release_vote_thread": schemas.tool_definition(
        description="Summarize likely votes and results in one Incubator release vote thread.",
        handler=summarize_release_vote_thread,
        properties=schemas.release_thread_summary_properties(),
        required=["message_id"],
    ),
    "podling_release_vote_history": schemas.tool_definition(
        description="Return likely release vote and result history for one Incubator podling.",
        handler=podling_release_vote_history,
        properties=schemas.podling_history_properties(),
        required=["podling"],
    ),
}
