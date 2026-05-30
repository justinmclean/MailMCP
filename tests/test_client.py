from __future__ import annotations

import sys
import unittest
from pathlib import Path
from typing import Any, cast
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from apache_incubator_mail_mcp import client
from tests.fixtures import (
    SAMPLE_EMAIL,
    SAMPLE_MBOX,
    SAMPLE_RELEASE_EMAILS,
    SAMPLE_RELEASE_STATS,
    SAMPLE_STATS,
    cache_dir,
)


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

    def test_find_release_vote_threads_filters_subjects(self) -> None:
        with mock.patch.object(client, "_read_json", return_value=SAMPLE_RELEASE_STATS):
            result = client.find_release_vote_threads(podling="Foo", limit=10)

        self.assertEqual(result["returned"], 1)
        self.assertEqual(result["threads"][0]["thread_id"], "thread-release-1")
        self.assertEqual(result["threads"][0]["message_count"], 2)

    def test_find_release_result_threads_filters_subjects(self) -> None:
        with mock.patch.object(client, "_read_json", return_value=SAMPLE_RELEASE_STATS):
            result = client.find_release_result_threads(podling="Foo", limit=10)

        self.assertEqual(result["returned"], 1)
        self.assertEqual(result["threads"][0]["sample_message_id"], "vote-result@1735862400@")

    def test_summarize_release_vote_thread_counts_votes(self) -> None:
        def fake_fetch_email(*, message_id: str, **_: Any) -> dict:
            return client.normalize_summary(SAMPLE_RELEASE_EMAILS[message_id]).to_dict() | {
                "body": SAMPLE_RELEASE_EMAILS[message_id]["body"],
            }

        with (
            mock.patch.object(client, "fetch_email", side_effect=fake_fetch_email),
            mock.patch.object(client, "fetch_mail_stats") as fetch_mail_stats,
        ):
            release_emails = cast(dict[str, dict[str, Any]], SAMPLE_RELEASE_STATS["emails"])
            fetch_mail_stats.return_value = {
                "list": "general@incubator.apache.org",
                "timespan": "lte=12M",
                "query": "Release Apache Foo 1.2.3",
                "hits": 3,
                "emails": [
                    client.normalize_summary(raw).to_dict() for raw in release_emails.values()
                ],
                "api_url": "https://example.test/api/stats.lua",
            }
            result = client.summarize_release_vote_thread(message_id="vote-root@1735689600@")

        self.assertEqual(result["message_count"], 3)
        self.assertEqual(result["votes"]["binding_plus_one"], 1)
        self.assertEqual(result["result"]["id"], "vote-result@1735862400@")

    def test_podling_release_vote_history_combines_votes_and_results(self) -> None:
        with mock.patch.object(client, "_read_json", return_value=SAMPLE_RELEASE_STATS):
            result = client.podling_release_vote_history(podling="Foo")

        self.assertEqual(result["podling"], "Foo")
        self.assertEqual(result["vote_count"], 1)
        self.assertEqual(result["result_count"], 1)

    def test_fetch_mail_stats_uses_explicit_list_and_domain(self) -> None:
        captured: dict[str, str] = {}

        def fake_read_json(url: str) -> dict[str, Any]:
            captured["url"] = url
            return {**SAMPLE_STATS, "list": "dev@iceberg.apache.org", "domain": "iceberg.apache.org"}

        with mock.patch.object(client, "_read_json", side_effect=fake_read_json):
            result = client.fetch_mail_stats(
                api_base="https://example.test/api",
                list_name="dev",
                domain="iceberg.apache.org",
                limit=2,
            )

        self.assertIn("list=dev", captured["url"])
        self.assertIn("domain=iceberg.apache.org", captured["url"])
        self.assertEqual(result["list"], "dev@iceberg.apache.org")
        self.assertEqual(result["domain"], "iceberg.apache.org")

    def test_validate_podling_list_rejects_unknown(self) -> None:
        for name in ("dev", "users", "commits"):
            self.assertEqual(client.validate_podling_list(name), name)
        with self.assertRaises(ValueError):
            client.validate_podling_list("private")
        with self.assertRaises(ValueError):
            client.validate_podling_list("")

    def test_validate_podling_name_normalizes_and_rejects_invalid(self) -> None:
        self.assertEqual(client.validate_podling_name("Pekko"), "pekko")
        self.assertEqual(client.validate_podling_name("foo-bar"), "foo-bar")
        with self.assertRaises(ValueError):
            client.validate_podling_name("")
        with self.assertRaises(ValueError):
            client.validate_podling_name("bad name")
        with self.assertRaises(ValueError):
            client.validate_podling_name("../etc/passwd")

    def test_resolve_podling_domain_prefers_flat_then_falls_back(self) -> None:
        calls: list[str] = []

        def fake_read_json(url: str) -> dict[str, Any]:
            calls.append(url)
            if "iceberg.apache.org" in url and "incubator" not in url:
                return {"hits": 0, "firstYear": None, "lastYear": None, "emails": []}
            return {"hits": 42, "firstYear": 2020, "lastYear": 2024, "emails": []}

        with mock.patch.object(client, "_read_json", side_effect=fake_read_json):
            resolved = client.resolve_podling_domain(podling="iceberg", list_name="dev")

        self.assertEqual(resolved, "iceberg.incubator.apache.org")
        self.assertEqual(len(calls), 2)
        self.assertIn("iceberg.apache.org", calls[0])
        self.assertIn("iceberg.incubator.apache.org", calls[1])

    def test_resolve_podling_domain_returns_flat_when_both_empty(self) -> None:
        empty = {"hits": 0, "firstYear": None, "lastYear": None, "emails": []}
        with mock.patch.object(client, "_read_json", return_value=empty):
            resolved = client.resolve_podling_domain(podling="newpod", list_name="dev")
        self.assertEqual(resolved, "newpod.apache.org")

    def test_cache_namespaces_non_default_lists(self) -> None:
        with cache_dir() as base:
            with mock.patch.object(client, "_read_json", return_value=SAMPLE_STATS):
                # General list -> root of cache_dir (backward compat).
                general = client.cache_mail_stats(cache_dir=base, limit=1)
                # Podling list -> per-list subdirectory.
                podling = client.cache_mail_stats(
                    cache_dir=base,
                    list_name="dev",
                    domain="iceberg.apache.org",
                    limit=1,
                )
                # Loading respects the same scoping.
                from_general = client.load_cached_mail(cache_dir=base, limit=10)
                from_podling = client.load_cached_mail(
                    cache_dir=base,
                    list_name="dev",
                    domain="iceberg.apache.org",
                    limit=10,
                )

        self.assertEqual(Path(general["cache_dir"]), Path(base).resolve())
        self.assertEqual(
            Path(podling["cache_dir"]).name,
            "dev_iceberg.apache.org",
        )
        # Caches don't leak across list/domain scopes.
        self.assertEqual(from_general["count"], 1)
        self.assertEqual(from_podling["count"], 1)

    def test_cache_mbox_uses_list_specific_filename(self) -> None:
        with cache_dir() as base:
            with mock.patch.object(client, "_read_text", return_value=SAMPLE_MBOX):
                result = client.cache_mbox(
                    cache_dir=base,
                    month="2024-04",
                    list_name="dev",
                    domain="iceberg.apache.org",
                )
        self.assertEqual(Path(result["path"]).name, "dev_iceberg.apache.org-2024-04.mbox")
        self.assertEqual(result["list"], "dev@iceberg.apache.org")


if __name__ == "__main__":
    unittest.main()
