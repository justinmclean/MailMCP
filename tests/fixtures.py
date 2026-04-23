from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Iterator

SAMPLE_STATS = {
    "took": 1234,
    "firstYear": 2026,
    "lastYear": 2026,
    "hits": 2,
    "domain": "incubator.apache.org",
    "name": "general",
    "list": "general@incubator.apache.org",
    "emails": {
        "one": {
            "id": "abc123@1713571200@",
            "epoch": 1713571200,
            "subject": "[DISCUSS] New podling proposal",
            "message-id": "<abc123@example.org>",
            "private": False,
            "from": "A Mentor <mentor@apache.org>",
            "attachments": 0,
        },
        "two": {
            "id": "def456@1713657600@",
            "epoch": 1713657600,
            "subject": "Re: [DISCUSS] New podling proposal",
            "message-id": "<def456@example.org>",
            "private": False,
            "from": "Another Mentor <another@apache.org>",
            "attachments": 1,
        },
    },
}

SAMPLE_EMAIL = {
    "mid": "abc123@1713571200@",
    "tid": "abc123@1713571200@",
    "epoch": 1713571200,
    "date": "2024/04/20 00:00:00",
    "subject": "[DISCUSS] New podling proposal",
    "message-id": "<abc123@example.org>",
    "private": False,
    "from": "A Mentor <mentor@apache.org>",
    "body": "Proposal discussion body.",
    "references": "",
    "in-reply-to": "",
    "list": "general@incubator.apache.org",
}

SAMPLE_RELEASE_STATS = {
    "took": 2345,
    "firstYear": 2025,
    "lastYear": 2025,
    "hits": 4,
    "domain": "incubator.apache.org",
    "name": "general",
    "list": "general@incubator.apache.org",
    "emails": {
        "vote": {
            "id": "vote-root@1735689600@",
            "tid": "thread-release-1",
            "epoch": 1735689600,
            "subject": "[VOTE] Release Apache Foo 1.2.3",
            "message-id": "<vote-root@example.org>",
            "private": False,
            "from": "Release Manager <rm@apache.org>",
            "attachments": 0,
        },
        "binding": {
            "id": "vote-binding@1735776000@",
            "tid": "thread-release-1",
            "epoch": 1735776000,
            "subject": "Re: [VOTE] Release Apache Foo 1.2.3",
            "message-id": "<vote-binding@example.org>",
            "private": False,
            "from": "Mentor <mentor@apache.org>",
            "attachments": 0,
        },
        "result": {
            "id": "vote-result@1735862400@",
            "tid": "thread-release-1",
            "epoch": 1735862400,
            "subject": "[RESULT][VOTE] Release Apache Foo 1.2.3",
            "message-id": "<vote-result@example.org>",
            "private": False,
            "from": "Release Manager <rm@apache.org>",
            "attachments": 0,
        },
        "discuss": {
            "id": "discuss@1735948800@",
            "tid": "thread-discuss-1",
            "epoch": 1735948800,
            "subject": "[DISCUSS] Release process",
            "message-id": "<discuss@example.org>",
            "private": False,
            "from": "Other <other@apache.org>",
            "attachments": 0,
        },
    },
}

SAMPLE_RELEASE_EMAILS = {
    "vote-root@1735689600@": {
        "mid": "vote-root@1735689600@",
        "tid": "thread-release-1",
        "epoch": 1735689600,
        "date": "2025/01/01 00:00:00",
        "subject": "[VOTE] Release Apache Foo 1.2.3",
        "message-id": "<vote-root@example.org>",
        "private": False,
        "from": "Release Manager <rm@apache.org>",
        "body": "Please vote on releasing Apache Foo 1.2.3.",
        "references": "",
        "in-reply-to": "",
        "list": "general@incubator.apache.org",
    },
    "vote-binding@1735776000@": {
        "mid": "vote-binding@1735776000@",
        "tid": "thread-release-1",
        "epoch": 1735776000,
        "date": "2025/01/02 00:00:00",
        "subject": "Re: [VOTE] Release Apache Foo 1.2.3",
        "message-id": "<vote-binding@example.org>",
        "private": False,
        "from": "Mentor <mentor@apache.org>",
        "body": "+1 binding\nChecked signatures and source release.",
        "references": "<vote-root@example.org>",
        "in-reply-to": "<vote-root@example.org>",
        "list": "general@incubator.apache.org",
    },
    "vote-result@1735862400@": {
        "mid": "vote-result@1735862400@",
        "tid": "thread-release-1",
        "epoch": 1735862400,
        "date": "2025/01/03 00:00:00",
        "subject": "[RESULT][VOTE] Release Apache Foo 1.2.3",
        "message-id": "<vote-result@example.org>",
        "private": False,
        "from": "Release Manager <rm@apache.org>",
        "body": "The vote passes with 1 binding +1.",
        "references": "<vote-root@example.org>",
        "in-reply-to": "<vote-root@example.org>",
        "list": "general@incubator.apache.org",
    },
}

SAMPLE_MBOX = """From mentor@apache.org Sat Apr 20 00:00:00 2024
Subject: [DISCUSS] New podling proposal
From: A Mentor <mentor@apache.org>

Proposal discussion body.

From another@apache.org Sun Apr 21 00:00:00 2024
Subject: Re: [DISCUSS] New podling proposal
From: Another Mentor <another@apache.org>

Reply body.
"""


@contextmanager
def cache_dir() -> Iterator[Path]:
    with TemporaryDirectory() as tmp:
        yield Path(tmp)
