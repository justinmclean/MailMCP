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
