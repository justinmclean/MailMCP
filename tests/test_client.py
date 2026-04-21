from __future__ import annotations

from pathlib import Path
import sys
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from apache_incubator_mail_mcp import client
from tests.fixtures import SAMPLE_EMAIL, SAMPLE_MBOX, SAMPLE_STATS, cache_dir


class ClientTests(unittest.TestCase):
    def test_fetch_mail_stats_normalizes_email_map(self) -> None:
        with mock.patch.object(client, "_read_json", return_value=SAMPLE_STATS):
            result = client.fetch_mail_stats(api_base="https://example.test/api", limit=1)

        self.assertEqual(result["hits"], 2)
        self.assertEqual(result["returned"], 1)
        self.assertEqual(result["emails"][0]["subject"], "Re: [DISCUSS] New podling proposal")
        self.assertIn("stats.lua", result["api_url"])

    def test_fetch_email_returns_body(self) -> None:
        with mock.patch.object(client, "_read_json", return_value=SAMPLE_EMAIL):
            result = client.fetch_email(message_id="abc123@1713571200@")

        self.assertEqual(result["body"], "Proposal discussion body.")
        self.assertEqual(result["message_id"], "<abc123@example.org>")

    def test_cache_and_find_mail(self) -> None:
        with cache_dir() as base:
            with mock.patch.object(client, "_read_json", return_value=SAMPLE_STATS):
                written = client.cache_mail_stats(cache_dir=base, limit=2)
            cached = client.load_cached_mail(cache_dir=base, query="podling")
            found = client.find_cached_mail(cache_dir=base, message_id="<abc123@example.org>")

        self.assertEqual(written["count"], 2)
        self.assertEqual(cached["count"], 2)
        self.assertEqual(found["subject"], "[DISCUSS] New podling proposal")

    def test_cache_mbox_range(self) -> None:
        with cache_dir() as base:
            with mock.patch.object(client, "_read_text", return_value=SAMPLE_MBOX):
                result = client.cache_mbox_range(
                    cache_dir=base,
                    start_month="2024-04",
                    end_month="2024-05",
                )
            listed = client.list_cached_mboxes(cache_dir=base)

        self.assertEqual(result["count"], 2)
        self.assertEqual(result["total_messages"], 4)
        self.assertEqual(listed["count"], 2)


if __name__ == "__main__":
    unittest.main()
