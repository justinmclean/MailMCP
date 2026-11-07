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

        # The [RESULT] mail is its own thread; it is linked, not counted as a
        # message of the vote thread.
        self.assertEqual(result["message_count"], 2)
        self.assertEqual(result["votes"]["binding_plus_one"], 1)
        self.assertEqual(result["votes"]["plus_one"], 1)
        self.assertEqual(result["result"]["id"], "vote-result@1735862400@")

    def test_podling_release_vote_history_combines_votes_and_results(self) -> None:
        with mock.patch.object(client, "_read_json", return_value=SAMPLE_RELEASE_STATS):
            result = client.podling_release_vote_history(podling="Foo")

        self.assertEqual(result["podling"], "Foo")
        self.assertEqual(result["vote_count"], 1)
        self.assertEqual(result["result_count"], 1)
        self.assertEqual(result["results"][0]["vote_level"], "ipmc")
        self.assertEqual(result["votes"][0]["result"]["id"], "vote-result@1735862400@")

    def test_release_result_subject_accepts_malformed_tag(self) -> None:
        subject = "RESULT][VOTE] Release Apache Foo 1.2.3"
        self.assertTrue(client._is_release_result_subject(subject))
        self.assertFalse(client._is_release_vote_subject(subject))
        self.assertEqual(
            client._subject_core(subject), client._subject_core("[VOTE] Release Apache Foo 1.2.3")
        )

    def test_release_key_ignores_naming_variants(self) -> None:
        self.assertEqual(
            client._release_key("[VOTE] Release Apache Fluss 0.9.1-incubating (RC1)"),
            client._release_key("[RESULT][VOTE] Release Fluss 0.9.1-incubating-rc1"),
        )
        self.assertNotEqual(
            client._release_key("[VOTE] Release Apache Fluss 0.9.1-incubating (RC1)"),
            client._release_key("[VOTE] Release Apache Fluss 0.9.1-incubating (RC2)"),
        )
        self.assertEqual(
            client._release_key("[VOTE] Release Apache Cloudberry (Incubating) 2.2.0-rc2"),
            client._release_key("[CANCEL][VOTE] Release Apache Cloudberry, Incubating, 2.2.0-rc2"),
        )

    def test_vote_history_marks_ppmc_result_posted_before_the_vote(self) -> None:
        def email(key: str, epoch: int, subject: str) -> dict[str, Any]:
            return {
                "id": f"{key}@{epoch}@",
                "epoch": epoch,
                "subject": subject,
                "from": "RM <rm@apache.org>",
            }

        stats = {
            **SAMPLE_RELEASE_STATS,
            "emails": {
                "ppmc": email("ppmc", 100, "[RESULT][VOTE] Release Apache Foo 1.2.3"),
                "vote": email("vote", 200, "[VOTE] Release Apache Foo 1.2.3"),
                "ipmc": email("ipmc", 300, "RESULT][VOTE] Release Apache Foo 1.2.3"),
            },
        }
        with mock.patch.object(client, "_read_json", return_value=stats):
            result = client.podling_release_vote_history(podling="Foo")

        self.assertEqual(result["result_count"], 2)
        levels = {item["root_message_id"]: item["vote_level"] for item in result["results"]}
        self.assertEqual(levels, {"ppmc@100@": "ppmc", "ipmc@300@": "ipmc"})
        self.assertEqual(result["votes"][0]["result"]["id"], "ipmc@300@")

    def test_vote_history_finds_result_posted_in_vote_thread(self) -> None:
        subject = "[VOTE] Release Apache Foo 1.2.3"
        stats = {
            **SAMPLE_RELEASE_STATS,
            "emails": {
                "vote": {
                    "id": "vote@100@",
                    "epoch": 100,
                    "subject": subject,
                    "from": "RM <rm@apache.org>",
                },
                "plus": {
                    "id": "plus@200@",
                    "epoch": 200,
                    "subject": f"Re: {subject}",
                    "from": "Mentor <m@apache.org>",
                },
                "close": {
                    "id": "close@300@",
                    "epoch": 300,
                    "subject": f"Re: {subject}",
                    "from": "RM <rm@apache.org>",
                },
            },
        }
        reply = {
            "id": "close@300@",
            "subject": f"Re: {subject}",
            "body": "The vote has passed with 3 binding +1 votes.",
        }

        def fake_read_json(url: str) -> dict[str, Any]:
            return reply if "email.lua" in url else stats

        with mock.patch.object(client, "_read_json", side_effect=fake_read_json):
            result = client.podling_release_vote_history(podling="Foo")

        self.assertEqual(result["result_count"], 0)
        self.assertEqual(result["votes"][0]["result"]["source"], "reply_in_vote_thread")
        self.assertEqual(result["votes"][0]["result"]["id"], "close@300@")

    def test_vote_history_splits_a_vote_called_again_with_the_same_subject(self) -> None:
        subject = "[VOTE] Release Apache Foo (incubating) 0.9.0-incubating"
        stats = {
            **SAMPLE_RELEASE_STATS,
            "emails": {
                "first": {
                    "id": "rc10@100@",
                    "epoch": 100,
                    "subject": subject,
                    "from": "RM <rm@apache.org>",
                },
                "minus": {
                    "id": "minus@200@",
                    "epoch": 200,
                    "subject": f"Re: {subject}",
                    "from": "IPMC <i@apache.org>",
                },
                "again": {
                    "id": "rc14@300@",
                    "epoch": 300,
                    "subject": subject,
                    "from": "RM via general <general@incubator.apache.org>",
                },
            },
        }
        call = {
            "id": "rc14@300@",
            "subject": subject,
            "body": "The vote will remain open for at least 72 hours and passes with at\n"
            "least 3 binding +1 votes from IPMC members.\n\n[ ] +1 approve\n",
        }

        def fake_read_json(url: str) -> dict[str, Any]:
            return call if "email.lua" in url else stats

        with mock.patch.object(client, "_read_json", side_effect=fake_read_json):
            result = client.podling_release_vote_history(podling="Foo")

        self.assertEqual(result["vote_count"], 2)
        by_root = {vote["root_message_id"]: vote for vote in result["votes"]}
        self.assertEqual(by_root["rc10@100@"]["message_count"], 2)
        self.assertEqual(by_root["rc14@300@"]["message_count"], 1)
        self.assertIsNone(by_root["rc10@100@"]["result"])
        self.assertIsNone(by_root["rc14@300@"]["result"])

    def test_vote_call_text_is_not_an_in_thread_result(self) -> None:
        subject = "[VOTE] Release Apache Foo 1.2.3"
        stats = {
            **SAMPLE_RELEASE_STATS,
            "emails": {
                "vote": {
                    "id": "vote@100@",
                    "epoch": 100,
                    "subject": subject,
                    "from": "RM <rm@apache.org>",
                },
                "resend": {
                    "id": "resend@200@",
                    "epoch": 200,
                    "subject": f"Re: {subject}",
                    "from": "RM via general <general@incubator.apache.org>",
                },
            },
        }
        reply = {
            "id": "resend@200@",
            "subject": f"Re: {subject}",
            "body": "Reminder: the vote will remain open for at least 72 hours and passes "
            "with at least 3 binding +1 votes.",
        }

        def fake_read_json(url: str) -> dict[str, Any]:
            return reply if "email.lua" in url else stats

        with mock.patch.object(client, "_read_json", side_effect=fake_read_json):
            result = client.podling_release_vote_history(podling="Foo")

        self.assertIsNone(result["votes"][0]["result"])

    def test_vote_history_links_a_cancel_mail_to_its_vote(self) -> None:
        subject = "[VOTE]Release Apache Foo (Incubating) 2.7.0(Round2)"
        stats = {
            **SAMPLE_RELEASE_STATS,
            "emails": {
                "vote": {
                    "id": "vote@100@",
                    "epoch": 100,
                    "subject": subject,
                    "from": "RM <rm@apache.org>",
                },
                "cancel": {
                    "id": "cancel@200@",
                    "epoch": 200,
                    "subject": f"[CANCEL]{subject}",
                    "from": "RM <rm@apache.org>",
                },
            },
        }
        with mock.patch.object(client, "_read_json", return_value=stats):
            result = client.podling_release_vote_history(podling="Foo")

        self.assertEqual(result["vote_count"], 1)
        self.assertEqual(result["cancel_count"], 1)
        self.assertEqual(result["votes"][0]["result"]["source"], "cancelled")
        self.assertEqual(result["votes"][0]["result"]["id"], "cancel@200@")

    def test_in_thread_result_needs_a_closed_vote(self) -> None:
        pattern = client.IN_THREAD_RESULT_RE
        self.assertIsNone(pattern.search("stop publishing release tags before the vote\npasses."))
        self.assertIsNone(pattern.search("The vote passes with at least 3 binding +1 votes."))
        self.assertIsNotNone(pattern.search("The vote for Foo 1.2.3\nhas passed."))
        self.assertIsNotNone(pattern.search("The vote passes with 3 binding +1 votes."))
        self.assertIsNotNone(pattern.search("This vote is now closed."))

    def test_vote_history_reads_a_cancel_posted_in_the_vote_thread(self) -> None:
        subject = "[VOTE] Release Apache Foo 1.2.3"
        stats = {
            **SAMPLE_RELEASE_STATS,
            "emails": {
                "vote": {
                    "id": "vote@100@",
                    "epoch": 100,
                    "subject": subject,
                    "from": "RM <rm@apache.org>",
                },
                "reply": {
                    "id": "reply@200@",
                    "epoch": 200,
                    "subject": f"Re: {subject}",
                    "from": "RM <rm@apache.org>",
                },
            },
        }
        reply = {
            "id": "reply@200@",
            "subject": f"Re: {subject}",
            "body": "Thanks for the -1. I am cancelling this vote and will fix the issues "
            "before the vote passes.",
        }

        def fake_read_json(url: str) -> dict[str, Any]:
            return reply if "email.lua" in url else stats

        with mock.patch.object(client, "_read_json", side_effect=fake_read_json):
            result = client.podling_release_vote_history(podling="Foo")

        self.assertEqual(result["votes"][0]["result"]["source"], "cancelled_in_vote_thread")

    def test_a_resent_vote_call_stays_in_the_same_thread(self) -> None:
        subject = "[VOTE] Release Apache Foo 1.2.3"
        messages = [
            {"id": "a", "epoch": 1000, "subject": subject, "from": "RM <rm@apache.org>"},
            {"id": "b", "epoch": 1660, "subject": subject, "from": "RM <rm@apache.org>"},
            {"id": "c", "epoch": 2000, "subject": f"Re: {subject}", "from": "M <m@apache.org>"},
            {
                "id": "d",
                "epoch": 1000 + 3 * 86400,
                "subject": subject,
                "from": "RM <rm@apache.org>",
            },
        ]
        threads = client._split_same_subject_threads(messages)
        self.assertEqual(
            [[item["id"] for item in thread] for thread in threads], [["a", "b", "c"], ["d"]]
        )

    def test_in_thread_cancel_wording(self) -> None:
        pattern = client.IN_THREAD_CANCEL_RE
        self.assertIsNotNone(pattern.search("It will be canceled, and I will restart it."))
        self.assertIsNotNone(pattern.search("This vote has been cancelled."))
        self.assertIsNone(pattern.search("+1 binding, checked signatures."))

    def test_a_result_closes_only_the_latest_earlier_vote(self) -> None:
        subject = "[VOTE] Release Apache Foo 1.2.3"
        votes: list[dict[str, Any]] = [
            {"subject": subject, "root_epoch": 100, "root_message_id": "first"},
            {"subject": subject, "root_epoch": 500, "root_message_id": "again"},
        ]
        results: list[dict[str, Any]] = [
            {"subject": f"[RESULT]{subject}", "root_epoch": 900, "root_message_id": "res"}
        ]
        with mock.patch.object(client, "fetch_email", side_effect=ValueError):
            client._link_results_to_votes(
                votes, results, api_base="x", list_name="general", domain="incubator.apache.org"
            )

        self.assertIsNone(votes[0]["result"])
        self.assertEqual(votes[1]["result"]["id"], "res")

    def test_subject_variants_are_recognised(self) -> None:
        self.assertTrue(client._is_release_vote_subject("[VOTE] Apache Toree 0.6.0-incubating RC5"))
        self.assertFalse(client._is_release_vote_subject("[VOTE] Graduate Apache Foo"))
        self.assertTrue(client.REPLY_PREFIX_RE.match("AW: [VOTE] Release Apache Foo 4.0.0 RC2"))
        self.assertTrue(client.REPLY_PREFIX_RE.match("WG: [VOTE] Release Apache Foo 4.0.0 RC3"))
        self.assertEqual(
            client._release_key("Subject: [RESULT][VOTE] Release Apache Foo - foo-sdk 0.9.0 (RC1)"),
            client._release_key("[VOTE] Release Apache Foo - foo-sdk 0.9.0 (RC1)"),
        )

    def test_localised_reply_joins_the_vote_thread(self) -> None:
        subject = "[VOTE] Release Apache Foo 4.0.0-incubating RC2"
        stats = {
            **SAMPLE_RELEASE_STATS,
            "emails": {
                "vote": {
                    "id": "vote@100@",
                    "epoch": 100,
                    "subject": subject,
                    "from": "RM <rm@apache.org>",
                },
                "aw": {
                    "id": "aw@200@",
                    "epoch": 200,
                    "subject": f"AW: {subject}",
                    "from": "Mentor <m@apache.org>",
                },
            },
        }
        with mock.patch.object(client, "_read_json", return_value=stats):
            result = client.podling_release_vote_history(podling="Foo")

        self.assertEqual(result["vote_count"], 1)
        self.assertEqual(result["votes"][0]["message_count"], 2)

    def test_restarting_the_vote_cancels_it(self) -> None:
        self.assertIsNotNone(
            client.IN_THREAD_CANCEL_RE.search(
                "We'll restart the vote once the updated RC is ready."
            )
        )

    def test_duplicate_message_ids_are_merged(self) -> None:
        emails = [
            {"id": "a", "message_id": "<x@example.com>"},
            {"id": "b", "message_id": "<x@example.com>"},
            {"id": "c", "message_id": ""},
        ]
        self.assertEqual([item["id"] for item in client._unique_messages(emails)], ["a", "c"])

    def test_sender_key_ignores_the_list_relay_name(self) -> None:
        self.assertEqual(
            client._sender_key("ConradJam via general <general@incubator.apache.org>"),
            client._sender_key("ConradJam <cz@apache.org>"),
        )

    def test_fetch_mail_stats_uses_explicit_list_and_domain(self) -> None:
        captured: dict[str, str] = {}

        def fake_read_json(url: str) -> dict[str, Any]:
            captured["url"] = url
            return {
                **SAMPLE_STATS,
                "list": "dev@iceberg.apache.org",
                "domain": "iceberg.apache.org",
            }

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
