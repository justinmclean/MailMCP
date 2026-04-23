from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen

DEFAULT_API_BASE = "https://lists.apache.org/api"
DEFAULT_CACHE_DIR = ".cache/incubator-general-mail"
DEFAULT_LIST = "general"
DEFAULT_DOMAIN = "incubator.apache.org"
DEFAULT_TIMESPAN = "lte=1M"
DEFAULT_SEARCH_TIMESPAN = "lte=12M"
USER_AGENT = "apache-incubator-mail-mcp/0.1.0"
REPLY_PREFIX_RE = re.compile(r"^(?:\s*(?:re|fwd?):\s*)+", re.IGNORECASE)
SUBJECT_TAG_RE = re.compile(r"\[[^\]]+\]")
VOTE_LINE_RE = re.compile(r"(?im)^\s*(?P<vote>[+-]1|0)\b")


@dataclass(frozen=True)
class MailSummary:
    id: str
    subject: str | None
    sender: str | None
    epoch: int | None
    date: str | None
    message_id: str | None
    thread_id: str | None
    list_name: str
    private: bool | None
    attachments: int | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "subject": self.subject,
            "from": self.sender,
            "epoch": self.epoch,
            "date": self.date,
            "message_id": self.message_id,
            "thread_id": self.thread_id,
            "list": self.list_name,
            "private": self.private,
            "attachments": self.attachments,
            "permalink": permalink(self.id),
        }


def _clean_api_base(api_base: str = DEFAULT_API_BASE) -> str:
    return api_base.rstrip("/")


def _read_json(url: str, timeout: float = 30.0) -> dict[str, Any]:
    request = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(request, timeout=timeout) as response:
        payload = response.read().decode("utf-8")
    data = json.loads(payload)
    if not isinstance(data, dict):
        raise ValueError("Pony Mail returned a non-object JSON payload")
    return data


def _read_text(url: str, timeout: float = 60.0) -> str:
    request = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(request, timeout=timeout) as response:
        return response.read().decode("utf-8", errors="replace")


def _api_url(api_base: str, endpoint: str, params: dict[str, Any]) -> str:
    clean_params = {key: value for key, value in params.items() if value not in (None, "")}
    return f"{_clean_api_base(api_base)}/{endpoint}?{urlencode(clean_params)}"


def permalink(message_id: str) -> str:
    return f"https://lists.apache.org/thread/{message_id}"


def _date_from_epoch(epoch: Any) -> str | None:
    if not isinstance(epoch, int) or isinstance(epoch, bool):
        return None
    return datetime.fromtimestamp(epoch, UTC).strftime("%Y-%m-%d %H:%M:%S UTC")


def _as_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return None


def _as_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    return None


def _mail_entries(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    if isinstance(value, dict):
        return [item for item in value.values() if isinstance(item, dict)]
    return []


def normalize_summary(raw: dict[str, Any], list_name: str = f"{DEFAULT_LIST}@{DEFAULT_DOMAIN}") -> MailSummary:
    epoch = _as_int(raw.get("epoch"))
    message_id = raw.get("message-id") or raw.get("message_id")
    mid = raw.get("mid") or raw.get("id") or message_id
    if not isinstance(mid, str) or not mid:
        raise ValueError("Email summary is missing a Pony Mail id")
    return MailSummary(
        id=mid,
        subject=raw.get("subject") if isinstance(raw.get("subject"), str) else None,
        sender=raw.get("from") if isinstance(raw.get("from"), str) else None,
        epoch=epoch,
        date=raw.get("date") if isinstance(raw.get("date"), str) else _date_from_epoch(epoch),
        message_id=message_id if isinstance(message_id, str) else None,
        thread_id=raw.get("tid") if isinstance(raw.get("tid"), str) else raw.get("irt"),
        list_name=raw.get("list") if isinstance(raw.get("list"), str) and raw.get("list") else list_name,
        private=_as_bool(raw.get("private")),
        attachments=_as_int(raw.get("attachments")),
    )


def fetch_mail_stats(
    *,
    api_base: str = DEFAULT_API_BASE,
    timespan: str = DEFAULT_TIMESPAN,
    query: str | None = None,
    limit: int | None = None,
) -> dict[str, Any]:
    url = _api_url(
        api_base,
        "stats.lua",
        {
            "list": DEFAULT_LIST,
            "domain": DEFAULT_DOMAIN,
            "d": timespan,
            "q": query,
            "emailsOnly": "true",
        },
    )
    payload = _read_json(url)
    list_name = payload.get("list")
    resolved_list = list_name if isinstance(list_name, str) and list_name else f"{DEFAULT_LIST}@{DEFAULT_DOMAIN}"
    emails = [item.to_dict() for item in _summaries_from_payload(payload, resolved_list)]
    emails.sort(key=lambda item: item.get("epoch") or 0, reverse=True)
    if limit is not None:
        emails = emails[:limit]
    return {
        "list": resolved_list,
        "domain": payload.get("domain") or DEFAULT_DOMAIN,
        "name": payload.get("name") or DEFAULT_LIST,
        "timespan": timespan,
        "query": query,
        "hits": payload.get("hits", len(emails)),
        "returned": len(emails),
        "first_year": payload.get("firstYear"),
        "last_year": payload.get("lastYear"),
        "took": payload.get("took"),
        "emails": emails,
        "api_url": url,
    }


def _summaries_from_payload(payload: dict[str, Any], list_name: str) -> list[MailSummary]:
    summaries: list[MailSummary] = []
    for raw in _mail_entries(payload.get("emails")):
        try:
            summaries.append(normalize_summary(raw, list_name))
        except ValueError:
            continue
    return summaries


def fetch_email(*, message_id: str, api_base: str = DEFAULT_API_BASE) -> dict[str, Any]:
    url = _api_url(api_base, "email.lua", {"id": message_id})
    payload = _read_json(url)
    if "error" in payload:
        raise ValueError(str(payload["error"]))
    summary = normalize_summary(payload).to_dict()
    return {
        **summary,
        "body": payload.get("body") if isinstance(payload.get("body"), str) else "",
        "references": payload.get("references"),
        "in_reply_to": payload.get("in-reply-to") or payload.get("irt"),
        "from_raw": payload.get("from_raw"),
        "list_raw": payload.get("list_raw"),
        "api_url": url,
    }


def find_release_vote_threads(
    *,
    api_base: str = DEFAULT_API_BASE,
    timespan: str = DEFAULT_SEARCH_TIMESPAN,
    podling: str | None = None,
    query: str | None = None,
    limit: int | None = None,
) -> dict[str, Any]:
    """Find likely Incubator podling release vote threads."""
    return _find_release_threads(
        api_base=api_base,
        timespan=timespan,
        podling=podling,
        query=query,
        limit=limit,
        kind="vote",
    )


def find_release_result_threads(
    *,
    api_base: str = DEFAULT_API_BASE,
    timespan: str = DEFAULT_SEARCH_TIMESPAN,
    podling: str | None = None,
    query: str | None = None,
    limit: int | None = None,
) -> dict[str, Any]:
    """Find likely Incubator podling release vote result threads."""
    return _find_release_threads(
        api_base=api_base,
        timespan=timespan,
        podling=podling,
        query=query,
        limit=limit,
        kind="result",
    )


def summarize_release_vote_thread(
    *,
    message_id: str,
    api_base: str = DEFAULT_API_BASE,
    timespan: str = DEFAULT_SEARCH_TIMESPAN,
    limit: int | None = None,
) -> dict[str, Any]:
    """Summarize likely votes and result messages in one release vote thread."""
    root = fetch_email(api_base=api_base, message_id=message_id)
    subject = root.get("subject") if isinstance(root.get("subject"), str) else ""
    thread_key = _thread_key(root)
    search_query = _release_search_query(None, _subject_search_text(subject))
    stats = fetch_mail_stats(api_base=api_base, timespan=timespan, query=search_query, limit=limit)
    summaries = [
        item
        for item in stats["emails"]
        if _thread_key(item) == thread_key or _normal_subject(str(item.get("subject") or "")) == _normal_subject(subject)
    ]
    if not any(item["id"] == root["id"] for item in summaries):
        summaries.append({key: value for key, value in root.items() if key != "body"})
    summaries.sort(key=lambda item: item.get("epoch") or 0)

    full_messages = []
    for item in summaries:
        try:
            message = fetch_email(api_base=api_base, message_id=str(item["id"]))
        except ValueError:
            message = item | {"body": ""}
        full_messages.append(message)
        vote = _extract_vote(message)
    messages = [
        {
            "id": message.get("id"),
            "subject": message.get("subject"),
            "from": message.get("from"),
            "date": message.get("date"),
            "vote": _extract_vote(message),
            "is_result": _is_release_result_subject(str(message.get("subject") or "")),
            "permalink": message.get("permalink"),
        }
        for message in full_messages
    ]

    votes = {"binding_plus_one": 0, "plus_one": 0, "zero": 0, "minus_one": 0}
    voters: list[dict[str, Any]] = []
    result_messages: list[dict[str, Any]] = []
    for full_message, message_summary in zip(full_messages, messages, strict=True):
        if message_summary["is_result"]:
            result_messages.append(message_summary)
        vote = message_summary["vote"]
        if vote is None:
            continue
        body = str(full_message.get("body") or "")
        binding = bool(re.search(r"\bbinding\b", body, re.IGNORECASE))
        if vote == "+1" and binding:
            votes["binding_plus_one"] += 1
        elif vote == "+1":
            votes["plus_one"] += 1
        elif vote == "0":
            votes["zero"] += 1
        elif vote == "-1":
            votes["minus_one"] += 1
        voters.append(
            {
                "from": message_summary["from"],
                "vote": vote,
                "binding": binding if vote == "+1" else False,
                "message_id": message_summary["id"],
            }
        )

    return {
        "thread": _thread_summary(root, len(summaries)),
        "timespan": timespan,
        "query": search_query,
        "message_count": len(messages),
        "votes": votes,
        "voters": voters,
        "result": result_messages[-1] if result_messages else None,
        "messages": messages,
        "api_url": stats["api_url"],
    }


def podling_release_vote_history(
    *,
    podling: str,
    api_base: str = DEFAULT_API_BASE,
    timespan: str = DEFAULT_SEARCH_TIMESPAN,
    limit: int | None = None,
) -> dict[str, Any]:
    """Return likely release vote and result history for one podling."""
    votes = find_release_vote_threads(
        api_base=api_base,
        timespan=timespan,
        podling=podling,
        limit=limit,
    )
    results = find_release_result_threads(
        api_base=api_base,
        timespan=timespan,
        podling=podling,
        limit=limit,
    )
    return {
        "podling": podling,
        "timespan": timespan,
        "vote_count": votes["returned"],
        "result_count": results["returned"],
        "votes": votes["threads"],
        "results": results["threads"],
        "sources": {
            "votes_api_url": votes["api_url"],
            "results_api_url": results["api_url"],
        },
    }


def _find_release_threads(
    *,
    api_base: str,
    timespan: str,
    podling: str | None,
    query: str | None,
    limit: int | None,
    kind: str,
) -> dict[str, Any]:
    search_query = _release_search_query(podling, query or ("RESULT release" if kind == "result" else "VOTE release"))
    stats = fetch_mail_stats(api_base=api_base, timespan=timespan, query=search_query, limit=None)
    predicate = _is_release_result_subject if kind == "result" else _is_release_vote_subject
    threads = _release_threads_from_emails(stats["emails"], predicate, podling)
    total = len(threads)
    if limit is not None:
        threads = threads[:limit]
    return {
        "list": stats["list"],
        "timespan": timespan,
        "podling": podling,
        "query": search_query,
        "hits": stats["hits"],
        "count": total,
        "returned": len(threads),
        "threads": threads,
        "api_url": stats["api_url"],
    }


def _release_search_query(podling: str | None, query: str | None) -> str:
    parts = [part for part in (podling, query) if part]
    return " ".join(parts) or "release vote"


def _subject_search_text(subject: str) -> str:
    cleaned = SUBJECT_TAG_RE.sub(" ", _strip_reply_prefix(subject))
    return " ".join(cleaned.split()) or subject


def _release_threads_from_emails(
    emails: list[dict[str, Any]],
    predicate: Any,
    podling: str | None,
) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for email in emails:
        subject = str(email.get("subject") or "")
        if not predicate(subject):
            continue
        if podling and podling.casefold() not in subject.casefold():
            continue
        grouped.setdefault(_thread_key(email), []).append(email)
    threads = [_thread_summary(max(items, key=lambda item: item.get("epoch") or 0), len(items)) for items in grouped.values()]
    threads.sort(key=lambda item: item.get("latest_epoch") or 0, reverse=True)
    return threads


def _thread_summary(email: dict[str, Any], message_count: int) -> dict[str, Any]:
    return {
        "thread_id": _thread_key(email),
        "subject": email.get("subject"),
        "normalized_subject": _normal_subject(str(email.get("subject") or "")),
        "latest_epoch": email.get("epoch"),
        "latest_date": email.get("date"),
        "latest_from": email.get("from"),
        "message_count": message_count,
        "sample_message_id": email.get("id"),
        "permalink": email.get("permalink"),
    }


def _thread_key(email: dict[str, Any]) -> str:
    for key in ("thread_id", "id", "message_id"):
        value = email.get(key)
        if isinstance(value, str) and value:
            return value
    return _normal_subject(str(email.get("subject") or ""))


def _normal_subject(subject: str) -> str:
    without_prefix = _strip_reply_prefix(subject)
    return " ".join(without_prefix.casefold().split())


def _strip_reply_prefix(subject: str) -> str:
    return REPLY_PREFIX_RE.sub("", subject).strip()


def _is_release_vote_subject(subject: str) -> bool:
    lowered = subject.casefold()
    if "result" in lowered:
        return False
    return "[vote]" in lowered and "release" in lowered


def _is_release_result_subject(subject: str) -> bool:
    lowered = subject.casefold()
    return ("[result]" in lowered or "[results]" in lowered) and "release" in lowered


def _extract_vote(message: dict[str, Any]) -> str | None:
    body = str(message.get("body") or "")
    match = VOTE_LINE_RE.search(body)
    if match:
        return match.group("vote")
    subject = str(message.get("subject") or "")
    subject_match = re.search(r"(?<!\w)([+-]1|0)(?!\w)", subject)
    if subject_match:
        return subject_match.group(1)
    return None


def cache_mail_stats(
    *,
    cache_dir: str | Path = DEFAULT_CACHE_DIR,
    api_base: str = DEFAULT_API_BASE,
    timespan: str = DEFAULT_TIMESPAN,
    query: str | None = None,
    limit: int | None = None,
) -> dict[str, Any]:
    stats = fetch_mail_stats(api_base=api_base, timespan=timespan, query=query, limit=limit)
    base = Path(cache_dir).expanduser().resolve()
    base.mkdir(parents=True, exist_ok=True)
    cached_at = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    written: list[dict[str, str]] = []
    for email in stats["emails"]:
        cache_id = cache_key(str(email["id"]))
        payload = {**email, "cached_at": cached_at, "source_query": query, "source_timespan": timespan}
        path = base / f"{cache_id}.json"
        path.write_text(json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True), encoding="utf-8")
        written.append({"id": str(email["id"]), "cache_id": cache_id, "path": str(path)})
    return {
        "cache_dir": str(base),
        "cached_at": cached_at,
        "count": len(written),
        "messages": written,
        "source": {
            "api_base": api_base,
            "timespan": timespan,
            "query": query,
            "hits": stats["hits"],
        },
    }


def cache_key(message_id: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9._-]+", "_", message_id.strip())
    return slug.strip("._-")[:160] or "message"


def load_cached_mail(
    *,
    cache_dir: str | Path = DEFAULT_CACHE_DIR,
    query: str | None = None,
    limit: int | None = None,
) -> dict[str, Any]:
    base = Path(cache_dir).expanduser().resolve()
    if not base.exists():
        return {"cache_dir": str(base), "count": 0, "emails": []}
    needle = query.casefold() if query else None
    rows: list[dict[str, Any]] = []
    for path in sorted(base.glob("*.json")):
        try:
            item = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(item, dict):
            continue
        haystack = "\n".join(str(item.get(key, "")) for key in ("subject", "from", "message_id", "id"))
        if needle and needle not in haystack.casefold():
            continue
        rows.append({**item, "path": str(path)})
    rows.sort(key=lambda item: item.get("epoch") or 0, reverse=True)
    total = len(rows)
    if limit is not None:
        rows = rows[:limit]
    return {"cache_dir": str(base), "count": total, "returned": len(rows), "emails": rows}


def find_cached_mail(
    *,
    message_id: str,
    cache_dir: str | Path = DEFAULT_CACHE_DIR,
) -> dict[str, Any]:
    base = Path(cache_dir).expanduser().resolve()
    candidates = [base / f"{cache_key(message_id)}.json"]
    if base.exists():
        candidates.extend(sorted(base.glob("*.json")))
    seen: set[Path] = set()
    for path in candidates:
        if path in seen or not path.exists():
            continue
        seen.add(path)
        try:
            item = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(item, dict):
            continue
        ids = {str(item.get(key, "")) for key in ("id", "message_id", "thread_id")}
        if message_id in ids or cache_key(message_id) == path.stem:
            return {**item, "path": str(path)}
    raise FileNotFoundError(f"Cached Incubator general mail not found: {message_id}")


def validate_month(value: str) -> str:
    if not re.fullmatch(r"\d{4}-\d{2}", value):
        raise ValueError("month must use YYYY-MM format")
    year, month = value.split("-")
    if not 1 <= int(month) <= 12:
        raise ValueError("month must use YYYY-MM format with a valid month")
    return f"{int(year):04d}-{int(month):02d}"


def month_range(start_month: str, end_month: str) -> list[str]:
    start = validate_month(start_month)
    end = validate_month(end_month)
    start_year, start_num = (int(part) for part in start.split("-"))
    end_year, end_num = (int(part) for part in end.split("-"))
    if (end_year, end_num) < (start_year, start_num):
        raise ValueError("end_month must be the same as or later than start_month")
    months: list[str] = []
    year = start_year
    month = start_num
    while (year, month) <= (end_year, end_num):
        months.append(f"{year:04d}-{month:02d}")
        month += 1
        if month > 12:
            year += 1
            month = 1
    return months


def _mbox_dir(cache_dir: str | Path) -> Path:
    return Path(cache_dir).expanduser().resolve() / "mbox"


def fetch_mbox(
    *,
    month: str,
    api_base: str = DEFAULT_API_BASE,
    header_from: str | None = None,
    header_subject: str | None = None,
    header_body: str | None = None,
) -> dict[str, Any]:
    resolved_month = validate_month(month)
    url = _api_url(
        api_base,
        "mbox.lua",
        {
            "list": f"{DEFAULT_LIST}@{DEFAULT_DOMAIN}",
            "date": resolved_month,
            "header_from": header_from,
            "header_subject": header_subject,
            "header_body": header_body,
        },
    )
    content = _read_text(url)
    return {
        "month": resolved_month,
        "content": content,
        "bytes": len(content.encode("utf-8")),
        "message_count": count_mbox_messages(content),
        "api_url": url,
    }


def count_mbox_messages(content: str) -> int:
    return sum(1 for line in content.splitlines() if line.startswith("From "))


def cache_mbox(
    *,
    month: str,
    cache_dir: str | Path = DEFAULT_CACHE_DIR,
    api_base: str = DEFAULT_API_BASE,
    header_from: str | None = None,
    header_subject: str | None = None,
    header_body: str | None = None,
) -> dict[str, Any]:
    payload = fetch_mbox(
        api_base=api_base,
        month=month,
        header_from=header_from,
        header_subject=header_subject,
        header_body=header_body,
    )
    base = _mbox_dir(cache_dir)
    base.mkdir(parents=True, exist_ok=True)
    path = base / f"general-incubator-{payload['month']}.mbox"
    path.write_text(payload["content"], encoding="utf-8")
    metadata = {
        "month": payload["month"],
        "path": str(path),
        "bytes": payload["bytes"],
        "message_count": payload["message_count"],
        "cached_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "api_url": payload["api_url"],
        "filters": {
            "header_from": header_from,
            "header_subject": header_subject,
            "header_body": header_body,
        },
    }
    metadata_path = path.with_suffix(".json")
    metadata_path.write_text(
        json.dumps(metadata, ensure_ascii=True, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return metadata | {"metadata_path": str(metadata_path)}


def cache_mbox_range(
    *,
    start_month: str,
    end_month: str,
    cache_dir: str | Path = DEFAULT_CACHE_DIR,
    api_base: str = DEFAULT_API_BASE,
    header_from: str | None = None,
    header_subject: str | None = None,
    header_body: str | None = None,
) -> dict[str, Any]:
    cached = [
        cache_mbox(
            api_base=api_base,
            cache_dir=cache_dir,
            month=month,
            header_from=header_from,
            header_subject=header_subject,
            header_body=header_body,
        )
        for month in month_range(start_month, end_month)
    ]
    return {
        "cache_dir": str(_mbox_dir(cache_dir)),
        "start_month": validate_month(start_month),
        "end_month": validate_month(end_month),
        "count": len(cached),
        "total_bytes": sum(item["bytes"] for item in cached),
        "total_messages": sum(item["message_count"] for item in cached),
        "mboxes": cached,
    }


def list_cached_mboxes(*, cache_dir: str | Path = DEFAULT_CACHE_DIR) -> dict[str, Any]:
    base = _mbox_dir(cache_dir)
    rows: list[dict[str, Any]] = []
    if base.exists():
        for path in sorted(base.glob("*.mbox")):
            metadata_path = path.with_suffix(".json")
            metadata: dict[str, Any] = {}
            if metadata_path.exists():
                try:
                    loaded = json.loads(metadata_path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    loaded = {}
                if isinstance(loaded, dict):
                    metadata = loaded
            rows.append(
                {
                    "month": metadata.get("month") or _month_from_mbox_name(path.name),
                    "path": str(path),
                    "metadata_path": str(metadata_path) if metadata_path.exists() else None,
                    "bytes": metadata.get("bytes") or path.stat().st_size,
                    "message_count": metadata.get("message_count"),
                    "cached_at": metadata.get("cached_at"),
                }
            )
    return {"cache_dir": str(base), "count": len(rows), "mboxes": rows}


def _month_from_mbox_name(name: str) -> str | None:
    match = re.search(r"(\d{4}-\d{2})", name)
    return match.group(1) if match else None
