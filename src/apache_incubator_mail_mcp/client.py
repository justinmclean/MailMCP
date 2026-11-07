from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parseaddr
from pathlib import Path
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen

DEFAULT_API_BASE = "https://lists.apache.org/api"
DEFAULT_CACHE_DIR = ".cache/incubator-general-mail"
DEFAULT_LIST = "general"
DEFAULT_DOMAIN = "incubator.apache.org"
DEFAULT_LIST_ADDRESS = f"{DEFAULT_LIST}@{DEFAULT_DOMAIN}"
DEFAULT_TIMESPAN = "lte=1M"
DEFAULT_SEARCH_TIMESPAN = "lte=12M"
# Probing for existence only — Pony Mail returns firstYear/lastYear for the
# whole archive regardless of window, so a tiny window is sufficient and
# cheaper for the server than a multi-year scan.
PODLING_PROBE_TIMESPAN = "lte=1M"
USER_AGENT = "apache-incubator-mail-mcp/0.1.0"
PODLING_PUBLIC_LISTS: tuple[str, ...] = ("dev", "users", "commits")
PODLING_FLAT_SUFFIX = "apache.org"
PODLING_INCUBATING_SUFFIX = "incubator.apache.org"
# Reply and forward prefixes, including those mail clients add in other
# languages: "AW:" and "WG:" (German), "SV:" and "VS:" (Nordic), "Antw:"
# (Dutch), "TR:" (French), "RIF:" (Italian), "ODP:" (Polish), "回复:" and
# "转发:" (Chinese).
REPLY_PREFIX_RE = re.compile(
    r"^(?:\s*(?:re|fwd?|fw|aw|wg|sv|vs|antw|tr|rif|odp|回复|答复|转发)\s*[:：]\s*)+",
    re.IGNORECASE,
)
# A "Subject:" label pasted into the subject line itself.
SUBJECT_LABEL_RE = re.compile(r"^\s*subject\s*:\s*", re.IGNORECASE)
# A release vote subject names the release, or at least a version or RC:
# "[VOTE] Apache Toree 0.6.0-incubating RC5" has no "Release".
RELEASE_HINT_RE = re.compile(r"\brelease\b|\b\d+\.\d+|\brc\s*\d+\b", re.IGNORECASE)
SUBJECT_TAG_RE = re.compile(r"\[[^\]]+\]")
# What is left of a malformed tag, such as "RESULT]" in "RESULT][VOTE]".
STRAY_TAG_RE = re.compile(r"\[?\b\w+\]")
RESULT_WORD_RE = re.compile(r"\bresults?\b")
CANCEL_WORD_RE = re.compile(r"\bcancel(?:l?ed|l?ing)?\b")
# A result posted as a reply in the vote thread, not a new thread. Only a
# vote that has closed counts: "has passed", "failed", "passes with 3
# binding +1", "is closed". "Before the vote passes" is not a result.
IN_THREAD_RESULT_RE = re.compile(
    r"\bvote\b[\s\S]{0,120}?\b(?:has\s+|have\s+)?(?:passed|failed)\b"
    r"|\bvote\s+passes\s+with\b(?!\s+at\s+least)"
    r"|\bvote\s+(?:is\s+(?:now\s+)?|has\s+been\s+)closed\b"
    r"|\bresults?\s+(?:of|for)\s+the\s+vote\b",
    re.IGNORECASE,
)
# A vote cancelled in a reply rather than a [CANCEL] mail.
IN_THREAD_CANCEL_RE = re.compile(
    r"\[cancel\]|\b(?:cancel(?:l?ing|l?ed)?|withdraw(?:ing|n)?)\s+(?:this|the|our)\s+(?:[\w.-]+\s+){0,3}vote\b"
    r"|\b(?:will\s+be|is|has\s+been)\s+(?:cancell?ed|withdrawn)\b"
    r"|\b(?:re-?start|restart|re-?call)\s+(?:the|this|a\s+new)\s+vote\b",
    re.IGNORECASE,
)
# A new vote call rather than its result: "The vote will remain open for at
# least 72 hours and passes with at least 3 binding +1 votes", or the
# unticked "[ ] +1" template.
VOTE_CALL_RE = re.compile(
    r"\bwill\s+(?:remain\s+|be\s+)?open\b|\bopen\s+for\s+at\s+least\b"
    r"|\bpasses\s+with\s+at\s+least\b|^\s*\[\s*\]\s*[+-]?[01]\b",
    re.IGNORECASE | re.MULTILINE,
)
# A call sent again by its sender within this time is a resend, not a new vote.
RESEND_WINDOW_SECONDS = 24 * 60 * 60
# The list relay suffix Pony Mail adds to a sender: "Name via general".
VIA_LIST_RE = re.compile(r"\s+via\s+\S+$")
# A vote is only ever read from the voter's own unquoted text: the leading
# token of a line, with quoted material and the quoted-reply attribution
# ("On ... wrote:") stripped first.
# A vote at the start of the voter's own line: "+1", "-1", "0" or "+0", or the
# ticked box of the vote template, "[X] +1 Release this as ...". An unticked
# "[ ] -1 Do not release ..." is the template, not a vote.
VOTE_TOKEN_RE = re.compile(r"^\s*(?:\[[xX]\]\s*)?(?P<vote>[+-]1|\+?0)(?![\w.+-])")
QUOTED_LINE_RE = re.compile(r"^\s*>")
ATTRIBUTION_START_RE = re.compile(r"^on\b", re.IGNORECASE)
ATTRIBUTION_END_RE = re.compile(r"wrote:\s*$", re.IGNORECASE)
# "non-binding", "non binding", "nonbinding" and "not binding" all mean the
# voter said their vote does not bind; they must be tested before "binding".
NON_BINDING_RE = re.compile(r"\b(?:non|not)[\s-]?binding\b", re.IGNORECASE)
BINDING_RE = re.compile(r"\bbinding\b", re.IGNORECASE)
BINDING_MARKER_RE = re.compile(r"\((?:(?:non|not)[\s-]?)?binding\b[^)]*\)", re.IGNORECASE)
_SLUG_RE = re.compile(r"[^A-Za-z0-9._-]+")


def list_address(list_name: str, domain: str) -> str:
    return f"{list_name}@{domain}"


def _list_slug(list_name: str, domain: str) -> str:
    slug = _SLUG_RE.sub("_", list_address(list_name, domain)).strip("._-")
    return slug or "list"


def _is_default_target(list_name: str, domain: str) -> bool:
    return list_name == DEFAULT_LIST and domain == DEFAULT_DOMAIN


def _resolve_cache_root(
    cache_dir: str | Path,
    list_name: str = DEFAULT_LIST,
    domain: str = DEFAULT_DOMAIN,
) -> Path:
    """Resolve the on-disk cache directory for a given list.

    For the historical general@incubator.apache.org target, returns the cache
    directory root as-is (backward compatible with pre-existing caches). For
    any other list/domain combination, returns a per-list subdirectory so
    multiple lists can coexist without colliding.
    """
    base = Path(cache_dir).expanduser().resolve()
    if _is_default_target(list_name, domain):
        return base
    return base / _list_slug(list_name, domain)


def validate_podling_list(list_name: str) -> str:
    if not isinstance(list_name, str):
        raise ValueError("list_name must be a string")
    name = list_name.strip().lower()
    if name not in PODLING_PUBLIC_LISTS:
        allowed = ", ".join(PODLING_PUBLIC_LISTS)
        raise ValueError(f"podling list_name must be one of: {allowed}")
    return name


def validate_podling_name(podling: str) -> str:
    if not isinstance(podling, str):
        raise ValueError("podling must be a string")
    name = podling.strip().lower()
    if not name:
        raise ValueError("podling must be a non-empty string")
    if not re.fullmatch(r"[a-z0-9][a-z0-9._-]*", name):
        raise ValueError(
            "podling must contain only lowercase letters, digits, dots, underscores, or hyphens"
        )
    return name


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


def normalize_summary(
    raw: dict[str, Any],
    list_name: str = DEFAULT_LIST_ADDRESS,
) -> MailSummary:
    epoch = _as_int(raw.get("epoch"))
    message_id = raw.get("message-id") or raw.get("message_id")
    mid = raw.get("mid") or raw.get("id") or message_id
    if not isinstance(mid, str) or not mid:
        raise ValueError("Email summary is missing a Pony Mail id")
    raw_list = raw.get("list")
    resolved_list = raw_list if isinstance(raw_list, str) and raw_list else list_name
    return MailSummary(
        id=mid,
        subject=raw.get("subject") if isinstance(raw.get("subject"), str) else None,
        sender=raw.get("from") if isinstance(raw.get("from"), str) else None,
        epoch=epoch,
        date=raw.get("date") if isinstance(raw.get("date"), str) else _date_from_epoch(epoch),
        message_id=message_id if isinstance(message_id, str) else None,
        thread_id=raw.get("tid") if isinstance(raw.get("tid"), str) else raw.get("irt"),
        list_name=resolved_list,
        private=_as_bool(raw.get("private")),
        attachments=_as_int(raw.get("attachments")),
    )


def fetch_mail_stats(
    *,
    api_base: str = DEFAULT_API_BASE,
    list_name: str = DEFAULT_LIST,
    domain: str = DEFAULT_DOMAIN,
    timespan: str = DEFAULT_TIMESPAN,
    query: str | None = None,
    limit: int | None = None,
) -> dict[str, Any]:
    default_address = list_address(list_name, domain)
    url = _api_url(
        api_base,
        "stats.lua",
        {
            "list": list_name,
            "domain": domain,
            "d": timespan,
            "q": query,
            "emailsOnly": "true",
        },
    )
    payload = _read_json(url)
    payload_list = payload.get("list")
    resolved_list = (
        payload_list if isinstance(payload_list, str) and payload_list else default_address
    )
    emails = _unique_messages(
        [item.to_dict() for item in _summaries_from_payload(payload, resolved_list)]
    )
    emails.sort(key=lambda item: item.get("epoch") or 0, reverse=True)
    if limit is not None:
        emails = emails[:limit]
    return {
        "list": resolved_list,
        "domain": payload.get("domain") or domain,
        "name": payload.get("name") or list_name,
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


def _unique_messages(emails: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep one entry per Message-ID; the archive can hold a message twice."""
    seen: set[str] = set()
    unique = []
    for email in emails:
        key = str(email.get("message_id") or "").strip()
        if key:
            if key in seen:
                continue
            seen.add(key)
        unique.append(email)
    return unique


def resolve_podling_domain(
    *,
    podling: str,
    list_name: str,
    api_base: str = DEFAULT_API_BASE,
) -> str:
    """Return the domain that actually serves a podling's mailing list.

    Tries ``<podling>.apache.org`` first, falls back to
    ``<podling>.incubator.apache.org``. If neither has archived activity, the
    flat (modern) domain is returned anyway so callers see a meaningful URL.
    """
    podling = validate_podling_name(podling)
    list_name = validate_podling_list(list_name)
    candidates = [
        f"{podling}.{PODLING_FLAT_SUFFIX}",
        f"{podling}.{PODLING_INCUBATING_SUFFIX}",
    ]
    for candidate in candidates:
        if _list_has_archive(api_base=api_base, list_name=list_name, domain=candidate):
            return candidate
    return candidates[0]


def _list_has_archive(*, api_base: str, list_name: str, domain: str) -> bool:
    url = _api_url(
        api_base,
        "stats.lua",
        {
            "list": list_name,
            "domain": domain,
            "d": PODLING_PROBE_TIMESPAN,
            "emailsOnly": "true",
        },
    )
    try:
        payload = _read_json(url)
    except (OSError, ValueError):
        return False
    if payload.get("firstYear") or payload.get("lastYear"):
        return True
    hits = payload.get("hits")
    if isinstance(hits, int) and hits > 0:
        return True
    return bool(_mail_entries(payload.get("emails")))


def fetch_podling_mail_stats(
    *,
    podling: str,
    list_name: str,
    api_base: str = DEFAULT_API_BASE,
    timespan: str = DEFAULT_TIMESPAN,
    query: str | None = None,
    limit: int | None = None,
    domain: str | None = None,
) -> dict[str, Any]:
    """Fetch mail stats for a podling list, auto-resolving the domain."""
    list_name = validate_podling_list(list_name)
    podling = validate_podling_name(podling)
    resolved_domain = domain or resolve_podling_domain(
        podling=podling, list_name=list_name, api_base=api_base
    )
    payload = fetch_mail_stats(
        api_base=api_base,
        list_name=list_name,
        domain=resolved_domain,
        timespan=timespan,
        query=query,
        limit=limit,
    )
    payload["podling"] = podling
    return payload


def _summaries_from_payload(payload: dict[str, Any], list_name: str) -> list[MailSummary]:
    summaries: list[MailSummary] = []
    for raw in _mail_entries(payload.get("emails")):
        try:
            summaries.append(normalize_summary(raw, list_name))
        except ValueError:
            continue
    return summaries


def fetch_email(
    *,
    message_id: str,
    api_base: str = DEFAULT_API_BASE,
    list_name: str = DEFAULT_LIST,
    domain: str = DEFAULT_DOMAIN,
) -> dict[str, Any]:
    # Pony Mail's email.lua looks up by id alone; list_name/domain are accepted for
    # symmetry with the rest of the API and to inform fallbacks/normalization.
    url = _api_url(api_base, "email.lua", {"id": message_id})
    payload = _read_json(url)
    if "error" in payload:
        raise ValueError(str(payload["error"]))
    summary = normalize_summary(payload, list_address(list_name, domain)).to_dict()
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
    list_name: str = DEFAULT_LIST,
    domain: str = DEFAULT_DOMAIN,
    timespan: str = DEFAULT_SEARCH_TIMESPAN,
    podling: str | None = None,
    query: str | None = None,
    limit: int | None = None,
) -> dict[str, Any]:
    """Find likely Incubator podling release vote threads."""
    return _find_release_threads(
        api_base=api_base,
        list_name=list_name,
        domain=domain,
        timespan=timespan,
        podling=podling,
        query=query,
        limit=limit,
        kind="vote",
    )


def find_release_result_threads(
    *,
    api_base: str = DEFAULT_API_BASE,
    list_name: str = DEFAULT_LIST,
    domain: str = DEFAULT_DOMAIN,
    timespan: str = DEFAULT_SEARCH_TIMESPAN,
    podling: str | None = None,
    query: str | None = None,
    limit: int | None = None,
) -> dict[str, Any]:
    """Find likely Incubator podling release vote result threads."""
    return _find_release_threads(
        api_base=api_base,
        list_name=list_name,
        domain=domain,
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
    list_name: str = DEFAULT_LIST,
    domain: str = DEFAULT_DOMAIN,
    timespan: str = DEFAULT_SEARCH_TIMESPAN,
    limit: int | None = None,
) -> dict[str, Any]:
    """Summarize the votes cast in one release vote thread.

    Only what the mail itself says is reported. A vote is read from the
    sender's own unquoted text, the [VOTE] call itself never counts as a
    vote, and the binding marker is recorded as the voter declared it
    (``declared_binding``). Deciding whether a voter is *actually* binding
    needs the IPMC roster and belongs to the caller, not here.
    """
    root = fetch_email(api_base=api_base, list_name=list_name, domain=domain, message_id=message_id)
    raw_subject = root.get("subject")
    subject = raw_subject if isinstance(raw_subject, str) else ""
    subject_core = _subject_core(subject)
    search_query = _release_search_query(None, _subject_search_text(subject))
    stats = fetch_mail_stats(
        api_base=api_base,
        list_name=list_name,
        domain=domain,
        timespan=timespan,
        query=search_query,
        limit=limit,
    )

    summaries = [
        item
        for item in stats["emails"]
        if _in_vote_thread(item, subject_core)
        # The lookup message anchors the thread even if the search missed it.
        or str(item.get("id") or "") == root["id"]
    ]
    if not any(item["id"] == root["id"] for item in summaries):
        summaries.append({key: value for key, value in root.items() if key != "body"})
    # Two votes on the same subject, such as an IPMC vote that was called
    # again, are separate threads. Keep the one this message is in.
    summaries = next(
        (
            thread
            for thread in _split_same_subject_threads(summaries)
            if any(str(item.get("id") or "") == root["id"] for item in thread)
        ),
        summaries,
    )

    full_messages = []
    for item in summaries:
        if str(item.get("id") or "") == root["id"]:
            full_messages.append(root)
            continue
        try:
            message = fetch_email(
                api_base=api_base,
                list_name=list_name,
                domain=domain,
                message_id=str(item["id"]),
            )
        except ValueError:
            message = item | {"body": ""}
        full_messages.append(message)

    opener_id = str(summaries[0]["id"]) if summaries else root["id"]
    messages = []
    for message in full_messages:
        is_opener = _is_vote_opener(message, opener_id)
        record = _vote_record(message, is_opener=is_opener)
        messages.append(
            {
                "id": message.get("id"),
                "subject": message.get("subject"),
                "from": message.get("from"),
                "date": message.get("date"),
                "epoch": message.get("epoch"),
                "vote": record["vote"],
                "declared_binding": record["declared_binding"],
                "is_opener": is_opener,
                "permalink": message.get("permalink"),
            }
        )

    voters = _deduplicate_voters(messages)
    votes = _vote_tally(voters)
    result = _find_vote_result(
        stats["emails"], subject_core, after_epoch=summaries[0].get("epoch") if summaries else None
    )

    opened = summaries[0].get("epoch") if summaries else None
    cancels = [
        email
        for email in stats["emails"]
        if _is_release_cancel_subject(str(email.get("subject") or ""))
        and _release_key(str(email.get("subject") or "")) == _release_key(subject_core)
        and (opened is None or (email.get("epoch") or 0) >= opened)
    ]
    cancel = min(cancels, key=lambda email: email.get("epoch") or 0) if cancels else None

    return {
        "thread": _thread_summary_from_messages(summaries),
        "timespan": timespan,
        "query": search_query,
        "message_count": len(messages),
        "votes": votes,
        "voters": voters,
        "result": result,
        "cancelled": (
            {
                "id": cancel.get("id"),
                "subject": cancel.get("subject"),
                "from": cancel.get("from"),
                "date": cancel.get("date"),
                "permalink": cancel.get("permalink"),
            }
            if cancel
            else None
        ),
        "messages": messages,
        "api_url": stats["api_url"],
    }


def _in_vote_thread(email: dict[str, Any], subject_core: str) -> bool:
    subject = str(email.get("subject") or "")
    return _is_release_vote_subject(subject) and _subject_core(subject) == subject_core


def _is_vote_opener(message: dict[str, Any], opener_id: str) -> bool:
    """True for the [VOTE] call itself, which is never a vote."""
    if str(message.get("id") or "") == opener_id:
        return True
    subject = str(message.get("subject") or "")
    return not REPLY_PREFIX_RE.match(subject) and _is_release_vote_subject(subject)


def _deduplicate_voters(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep one vote per person: the last one they cast.

    Voters are keyed on their display name where they have one, so the same
    person posting from two addresses is merged.
    """
    latest: dict[str, dict[str, Any]] = {}
    for message in messages:
        if message["vote"] is None:
            continue
        key, name, address = _voter_identity(message.get("from"))
        latest[key] = {
            "from": message.get("from"),
            "name": name,
            "address": address,
            "vote": message["vote"],
            "declared_binding": message["declared_binding"],
            "message_id": message.get("id"),
            "date": message.get("date"),
            "permalink": message.get("permalink"),
        }
    return sorted(latest.values(), key=lambda voter: str(voter.get("date") or ""))


def _voter_identity(sender: Any) -> tuple[str, str | None, str | None]:
    raw = str(sender or "").strip()
    name, address = parseaddr(raw)
    name = name.strip().strip('"').strip()
    address = address.strip().casefold()
    if name:
        return " ".join(name.casefold().split()), name, address or None
    if address:
        return address, None, address
    return raw.casefold() or "unknown", None, None


def _vote_tally(voters: list[dict[str, Any]]) -> dict[str, int]:
    tally = {
        "plus_one": 0,
        "zero": 0,
        "minus_one": 0,
        "binding_plus_one": 0,
        "binding_zero": 0,
        "binding_minus_one": 0,
    }
    names = {"+1": "plus_one", "0": "zero", "-1": "minus_one"}
    for voter in voters:
        name = names.get(str(voter["vote"]))
        if name is None:
            continue
        tally[name] += 1
        if voter["declared_binding"] is True:
            tally[f"binding_{name}"] += 1
    return tally


def _find_vote_result(
    emails: list[dict[str, Any]], subject_core: str, *, after_epoch: Any = None
) -> dict[str, Any] | None:
    """Link the separate [RESULT] thread for the same release candidate.

    With ``after_epoch``, the first result sent after the vote opened is
    used, so an earlier PPMC result or an earlier vote's result is skipped.
    """
    candidates = [
        email
        for email in emails
        if _is_release_result_subject(str(email.get("subject") or ""))
        and _release_key(str(email.get("subject") or "")) == _release_key(subject_core)
    ]
    if after_epoch is not None:
        candidates = [email for email in candidates if (email.get("epoch") or 0) >= after_epoch]
        if not candidates:
            return None
        latest = min(candidates, key=lambda email: email.get("epoch") or 0)
    elif not candidates:
        return None
    else:
        latest = max(candidates, key=lambda email: email.get("epoch") or 0)
    return {
        "id": latest.get("id"),
        "subject": latest.get("subject"),
        "from": latest.get("from"),
        "date": latest.get("date"),
        "epoch": latest.get("epoch"),
        "permalink": latest.get("permalink"),
        "thread_id": _thread_key(latest),
    }


def podling_release_vote_history(
    *,
    podling: str,
    api_base: str = DEFAULT_API_BASE,
    list_name: str = DEFAULT_LIST,
    domain: str = DEFAULT_DOMAIN,
    timespan: str = DEFAULT_SEARCH_TIMESPAN,
    limit: int | None = None,
) -> dict[str, Any]:
    """Return likely release vote and result history for one podling."""
    votes = find_release_vote_threads(
        api_base=api_base,
        list_name=list_name,
        domain=domain,
        timespan=timespan,
        podling=podling,
        limit=limit,
    )
    results = find_release_result_threads(
        api_base=api_base,
        list_name=list_name,
        domain=domain,
        timespan=timespan,
        podling=podling,
        limit=limit,
    )
    vote_threads = votes["threads"]
    result_threads = results["threads"]
    _link_cancels_to_votes(vote_threads, votes.get("cancel_threads") or [])
    _link_results_to_votes(
        vote_threads, result_threads, api_base=api_base, list_name=list_name, domain=domain
    )
    return {
        "podling": podling,
        "timespan": timespan,
        "vote_count": votes["returned"],
        "result_count": results["returned"],
        # A reply to a cancel can carry its own tag ("[WIP] - Re: [CANCEL]..."),
        # so count the releases cancelled rather than the threads.
        "cancel_count": len(
            {
                _release_key(str(item.get("subject") or ""))
                for item in votes.get("cancel_threads") or []
            }
        ),
        "votes": vote_threads,
        "results": result_threads,
        "sources": {
            "votes_api_url": votes["api_url"],
            "results_api_url": results["api_url"],
        },
    }


def _link_cancels_to_votes(
    vote_threads: list[dict[str, Any]], cancel_threads: list[dict[str, Any]]
) -> None:
    """Mark each vote closed by a later [CANCEL] mail for the same release."""
    for vote in sorted(vote_threads, key=lambda item: item.get("root_epoch") or 0):
        key = _release_key(str(vote.get("subject") or ""))
        vote_epoch = vote.get("root_epoch") or 0
        cancels = [
            cancel
            for cancel in cancel_threads
            if _release_key(str(cancel.get("subject") or "")) == key
            and (cancel.get("root_epoch") or 0) >= vote_epoch
            and not cancel.get("_used")
        ]
        if cancels:
            cancel = min(cancels, key=lambda item: item.get("root_epoch") or 0)
            cancel["_used"] = True
            vote["result"] = _result_link(cancel, "cancelled")
    for cancel in cancel_threads:
        cancel.pop("_used", None)


def _link_results_to_votes(
    vote_threads: list[dict[str, Any]],
    result_threads: list[dict[str, Any]],
    *,
    api_base: str,
    list_name: str,
    domain: str,
) -> None:
    """Attach each vote's result and say which vote each result closes.

    A PPMC result is often cross-posted to general@ with the same subject as
    the IPMC result. It comes before the general@ vote opens, so a result
    dated before the matching vote's root is the PPMC one. When no separate
    result exists, the release manager may have posted it as a reply in the
    vote thread, so the latest message is read if the opener sent it.
    """
    votes_by_key: dict[str, list[dict[str, Any]]] = {}
    for vote in vote_threads:
        votes_by_key.setdefault(_release_key(str(vote.get("subject") or "")), []).append(vote)

    ordered_results = sorted(result_threads, key=lambda item: item.get("root_epoch") or 0)
    for result in ordered_results:
        matches = votes_by_key.get(_release_key(str(result.get("subject") or "")), [])
        result_epoch = result.get("root_epoch") or 0
        if not matches:
            result["vote_level"] = "unknown"
        elif any((vote.get("root_epoch") or 0) > result_epoch for vote in matches):
            # Another vote on this release opened later, so this result closed
            # the earlier PPMC vote.
            result["vote_level"] = "ppmc"
        else:
            result["vote_level"] = "ipmc"
        # A result closes the latest vote opened before it, not an earlier
        # vote on the same release that was cancelled or called again.
        earlier = [
            vote
            for vote in matches
            if "result" not in vote and (vote.get("root_epoch") or 0) <= result_epoch
        ]
        if earlier:
            vote = max(earlier, key=lambda item: item.get("root_epoch") or 0)
            vote["result"] = _result_link(result, "result_thread")

    for vote in vote_threads:
        if "result" in vote:
            continue
        vote["result"] = None
        latest_id = vote.get("latest_message_id")
        if (
            not latest_id
            or latest_id == vote.get("root_message_id")
            or _sender_key(vote.get("latest_from")) != _sender_key(vote.get("root_from"))
        ):
            continue
        try:
            message = fetch_email(
                api_base=api_base, list_name=list_name, domain=domain, message_id=str(latest_id)
            )
        except (OSError, ValueError):
            continue
        body = unquoted_body(str(message.get("body") or ""))
        if IN_THREAD_CANCEL_RE.search(body):
            source = "cancelled_in_vote_thread"
        elif IN_THREAD_RESULT_RE.search(body) and not VOTE_CALL_RE.search(body):
            source = "reply_in_vote_thread"
        else:
            continue
        vote["result"] = {
            "source": source,
            "id": latest_id,
            "from": vote.get("latest_from"),
            "date": vote.get("latest_date"),
            "permalink": permalink(str(latest_id)),
        }


def _sender_key(sender: Any) -> str:
    """Identify a sender across addresses and the "via <list>" relay name."""
    raw = str(sender or "").strip()
    name, address = parseaddr(raw)
    name = VIA_LIST_RE.sub("", name.strip().strip('"').strip())
    if name:
        return " ".join(name.casefold().split())
    return address.strip().casefold() or raw.casefold()


def _split_same_subject_threads(messages: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    """Split messages sharing one subject into threads, oldest first.

    Pony Mail search returns no thread ids, so threads are grouped by
    subject. A message without a Re: prefix opens a new thread, as when a
    vote is called again with the same subject; replies join the thread
    open at the time.
    """
    threads: list[list[dict[str, Any]]] = []
    for message in sorted(messages, key=lambda item: item.get("epoch") or 0):
        is_reply = bool(REPLY_PREFIX_RE.match(str(message.get("subject") or "")))
        if threads and (is_reply or _is_resend(threads[-1], message)):
            threads[-1].append(message)
        else:
            threads.append([message])
    return threads


def _is_resend(thread: list[dict[str, Any]], message: dict[str, Any]) -> bool:
    """True for the same call sent again soon after, before anyone else replied.

    A release manager sometimes sends a call twice within minutes. A call
    sent after someone else has replied, such as after a -1, is a new vote.
    """
    opener = thread[0]
    sender = _sender_key(opener.get("from"))
    gap = (message.get("epoch") or 0) - (opener.get("epoch") or 0)
    return (
        0 <= gap <= RESEND_WINDOW_SECONDS
        and _sender_key(message.get("from")) == sender
        and all(_sender_key(item.get("from")) == sender for item in thread)
    )


def _release_key(subject: str) -> str:
    """Reduce a subject to the release candidate it names.

    Podlings name the same candidate differently from one mail to the next:
    "Apache Fluss 0.9.1-incubating (RC1)", "Fluss 0.9.1-incubating-rc1",
    "Cloudberry, Incubating, 2.2.0-rc2". The words "release" and "vote", and
    an outcome such as "PASSED", are dropped, since cancel and result mails
    add or leave them out: "[CANCEL] Apache Fesod 2.1.0-incubating RC2",
    "[RESULT] [VOTE] Release Apache Asyncband 0.7.2 PASSED".
    """
    core = _subject_core(subject)
    core = re.sub(
        r"\bapache\b|\(?\bincubating\b\)?|[(),]"
        r"|\b(?:release|vote|passed|failed|approved|cancell?ed)\b"
        r"|\b(?:re|fwd?|aw|wg|sv)\s*:|(?:^|\s)-(?=\s)",
        " ",
        core,
    )
    core = re.sub(r"[-_\s]+rc\s*(\d+)", r" rc\1", core)
    core = re.sub(r"(\d)-(?=\s|$)", r"\1", core)
    return " ".join(core.split())


def _result_link(result: dict[str, Any], source: str) -> dict[str, Any]:
    return {
        "source": source,
        "id": result.get("root_message_id"),
        "from": result.get("root_from"),
        "date": result.get("root_date"),
        "permalink": result.get("permalink"),
    }


def _find_release_threads(
    *,
    api_base: str,
    list_name: str,
    domain: str,
    timespan: str,
    podling: str | None,
    query: str | None,
    limit: int | None,
    kind: str,
) -> dict[str, Any]:
    default_query = "RESULT release" if kind == "result" else "VOTE release"
    search_query = _release_search_query(podling, query or default_query)
    stats = fetch_mail_stats(
        api_base=api_base,
        list_name=list_name,
        domain=domain,
        timespan=timespan,
        query=search_query,
        limit=None,
    )
    predicate = _is_release_result_subject if kind == "result" else _is_release_vote_subject
    threads = _release_threads_from_emails(stats["emails"], predicate, podling)
    cancel_threads = (
        _release_threads_from_emails(stats["emails"], _is_release_cancel_subject, podling)
        if kind == "vote"
        else []
    )
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
        "cancel_threads": cancel_threads,
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
        grouped.setdefault(_normal_subject(subject), []).append(email)
    threads = [
        _thread_summary_from_messages(thread)
        for items in grouped.values()
        for thread in _split_same_subject_threads(items)
    ]
    threads.sort(key=lambda item: item.get("latest_epoch") or 0, reverse=True)
    return threads


def _thread_summary_from_messages(messages: list[dict[str, Any]]) -> dict[str, Any]:
    """Summarize a thread from all of its messages.

    Pony Mail's stats endpoint does not return a thread id, so replies are
    grouped by normalized subject and the thread is identified by its root
    (earliest) message, which is what lists.apache.org permalinks use.
    """
    ordered = sorted(messages, key=lambda item: item.get("epoch") or 0)
    root = ordered[0]
    latest = ordered[-1]
    return {
        "thread_id": _thread_key(root),
        "subject": root.get("subject"),
        "normalized_subject": _normal_subject(str(root.get("subject") or "")),
        "root_message_id": root.get("id"),
        "root_date": root.get("date"),
        "root_from": root.get("from"),
        "root_epoch": root.get("epoch"),
        "latest_epoch": latest.get("epoch"),
        "latest_date": latest.get("date"),
        "latest_from": latest.get("from"),
        "latest_message_id": latest.get("id"),
        "message_count": len(ordered),
        "sample_message_id": root.get("id"),
        "permalink": root.get("permalink") or permalink(str(root.get("id") or "")),
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
    return REPLY_PREFIX_RE.sub("", SUBJECT_LABEL_RE.sub("", subject)).strip()


def _is_release_vote_subject(subject: str) -> bool:
    lowered = subject.casefold()
    if RESULT_WORD_RE.search(lowered) or CANCEL_WORD_RE.search(lowered):
        return False
    return "[vote]" in lowered and bool(RELEASE_HINT_RE.search(lowered))


def _is_release_cancel_subject(subject: str) -> bool:
    # "[CANCEL][VOTE] Release Foo 1.2.3", or just "[CANCEL] Apache Foo 1.2.3 RC2".
    lowered = subject.casefold()
    return (
        bool(CANCEL_WORD_RE.search(lowered))
        and not RESULT_WORD_RE.search(lowered)
        and bool(RELEASE_HINT_RE.search(lowered))
    )


def _is_release_result_subject(subject: str) -> bool:
    # Matches "[RESULT]" and malformed tags such as "RESULT][VOTE]".
    lowered = subject.casefold()
    return bool(RESULT_WORD_RE.search(lowered)) and bool(RELEASE_HINT_RE.search(lowered))


def _subject_core(subject: str) -> str:
    """Normalize a subject to the release it is about, tags and Re: removed."""
    cleaned = SUBJECT_TAG_RE.sub(" ", _strip_reply_prefix(subject))
    cleaned = STRAY_TAG_RE.sub(" ", cleaned)
    return " ".join(cleaned.casefold().split())


def unquoted_body(body: str) -> str:
    """Return only the sender's own text.

    Drops quoted lines and everything from the quoted-reply attribution
    ("On <date>, <someone> wrote:") onwards, so a vote quoted from an earlier
    message is never mistaken for a vote of the sender's own.
    """
    lines = body.splitlines()
    kept: list[str] = []
    for index, line in enumerate(lines):
        if QUOTED_LINE_RE.match(line):
            continue
        if _is_quote_attribution(lines, index):
            break
        kept.append(line)
    return "\n".join(kept)


def _is_quote_attribution(lines: list[str], index: int) -> bool:
    first = lines[index].strip()
    if not ATTRIBUTION_START_RE.match(first):
        return False
    joined = first
    # The attribution often wraps over the next line or two.
    for extra in lines[index + 1 : index + 3]:
        if ATTRIBUTION_END_RE.search(joined):
            break
        joined = f"{joined} {extra.strip()}"
    return bool(ATTRIBUTION_END_RE.search(joined))


def _vote_record(message: dict[str, Any], *, is_opener: bool) -> dict[str, Any]:
    """Read the vote and the voter's own binding marker from one message."""
    if is_opener:
        return {"vote": None, "declared_binding": None}
    body = unquoted_body(str(message.get("body") or ""))
    for line in body.splitlines():
        match = VOTE_TOKEN_RE.match(line)
        if match is None:
            continue
        vote = match.group("vote")
        return {
            "vote": "0" if vote == "+0" else vote,
            "declared_binding": _declared_binding(line, body),
        }
    return {"vote": None, "declared_binding": None}


def _declared_binding(vote_line: str, body: str) -> bool | None:
    """What the voter said about their own vote, not what the roster says.

    Most voters write no marker at all, which is None (unknown), never True.
    Whether an unmarked voter is in fact binding can only be settled against
    the IPMC roster, which is the caller's job.
    """
    if NON_BINDING_RE.search(vote_line):
        return False
    if BINDING_RE.search(vote_line):
        return True
    marker = BINDING_MARKER_RE.search(body)
    if marker is None:
        return None
    return not NON_BINDING_RE.search(marker.group(0))


def cache_mail_stats(
    *,
    cache_dir: str | Path = DEFAULT_CACHE_DIR,
    api_base: str = DEFAULT_API_BASE,
    list_name: str = DEFAULT_LIST,
    domain: str = DEFAULT_DOMAIN,
    timespan: str = DEFAULT_TIMESPAN,
    query: str | None = None,
    limit: int | None = None,
) -> dict[str, Any]:
    stats = fetch_mail_stats(
        api_base=api_base,
        list_name=list_name,
        domain=domain,
        timespan=timespan,
        query=query,
        limit=limit,
    )
    base = _resolve_cache_root(cache_dir, list_name, domain)
    base.mkdir(parents=True, exist_ok=True)
    cached_at = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    written: list[dict[str, str]] = []
    for email in stats["emails"]:
        cache_id = cache_key(str(email["id"]))
        payload = {
            **email,
            "cached_at": cached_at,
            "source_query": query,
            "source_timespan": timespan,
            "source_list": list_address(list_name, domain),
        }
        path = base / f"{cache_id}.json"
        path.write_text(
            json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        written.append({"id": str(email["id"]), "cache_id": cache_id, "path": str(path)})
    return {
        "cache_dir": str(base),
        "cached_at": cached_at,
        "count": len(written),
        "messages": written,
        "source": {
            "api_base": api_base,
            "list": list_address(list_name, domain),
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
    list_name: str = DEFAULT_LIST,
    domain: str = DEFAULT_DOMAIN,
    query: str | None = None,
    limit: int | None = None,
) -> dict[str, Any]:
    base = _resolve_cache_root(cache_dir, list_name, domain)
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
        haystack = "\n".join(
            str(item.get(key, "")) for key in ("subject", "from", "message_id", "id")
        )
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
    list_name: str = DEFAULT_LIST,
    domain: str = DEFAULT_DOMAIN,
) -> dict[str, Any]:
    base = _resolve_cache_root(cache_dir, list_name, domain)
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


def _mbox_dir(
    cache_dir: str | Path,
    list_name: str = DEFAULT_LIST,
    domain: str = DEFAULT_DOMAIN,
) -> Path:
    return _resolve_cache_root(cache_dir, list_name, domain) / "mbox"


def _mbox_filename(list_name: str, domain: str, month: str) -> str:
    if _is_default_target(list_name, domain):
        return f"general-incubator-{month}.mbox"
    return f"{_list_slug(list_name, domain)}-{month}.mbox"


def fetch_mbox(
    *,
    month: str,
    api_base: str = DEFAULT_API_BASE,
    list_name: str = DEFAULT_LIST,
    domain: str = DEFAULT_DOMAIN,
    header_from: str | None = None,
    header_subject: str | None = None,
    header_body: str | None = None,
) -> dict[str, Any]:
    resolved_month = validate_month(month)
    url = _api_url(
        api_base,
        "mbox.lua",
        {
            "list": list_address(list_name, domain),
            "date": resolved_month,
            "header_from": header_from,
            "header_subject": header_subject,
            "header_body": header_body,
        },
    )
    content = _read_text(url)
    return {
        "month": resolved_month,
        "list": list_address(list_name, domain),
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
    list_name: str = DEFAULT_LIST,
    domain: str = DEFAULT_DOMAIN,
    header_from: str | None = None,
    header_subject: str | None = None,
    header_body: str | None = None,
) -> dict[str, Any]:
    payload = fetch_mbox(
        api_base=api_base,
        list_name=list_name,
        domain=domain,
        month=month,
        header_from=header_from,
        header_subject=header_subject,
        header_body=header_body,
    )
    base = _mbox_dir(cache_dir, list_name, domain)
    base.mkdir(parents=True, exist_ok=True)
    path = base / _mbox_filename(list_name, domain, payload["month"])
    path.write_text(payload["content"], encoding="utf-8")
    metadata = {
        "month": payload["month"],
        "list": list_address(list_name, domain),
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
    list_name: str = DEFAULT_LIST,
    domain: str = DEFAULT_DOMAIN,
    header_from: str | None = None,
    header_subject: str | None = None,
    header_body: str | None = None,
) -> dict[str, Any]:
    cached = [
        cache_mbox(
            api_base=api_base,
            cache_dir=cache_dir,
            list_name=list_name,
            domain=domain,
            month=month,
            header_from=header_from,
            header_subject=header_subject,
            header_body=header_body,
        )
        for month in month_range(start_month, end_month)
    ]
    return {
        "cache_dir": str(_mbox_dir(cache_dir, list_name, domain)),
        "list": list_address(list_name, domain),
        "start_month": validate_month(start_month),
        "end_month": validate_month(end_month),
        "count": len(cached),
        "total_bytes": sum(item["bytes"] for item in cached),
        "total_messages": sum(item["message_count"] for item in cached),
        "mboxes": cached,
    }


def list_cached_mboxes(
    *,
    cache_dir: str | Path = DEFAULT_CACHE_DIR,
    list_name: str = DEFAULT_LIST,
    domain: str = DEFAULT_DOMAIN,
) -> dict[str, Any]:
    base = _mbox_dir(cache_dir, list_name, domain)
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
