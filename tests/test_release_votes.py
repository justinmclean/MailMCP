"""Regression tests for release vote thread summarization.

Every message here is a real one from the Apache Cloudberry (Incubating)
2.1.0-rc1 and 2.1.0-rc2 vote threads on general@incubator.apache.org.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from typing import Any
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from apache_incubator_mail_mcp import client
from tests.fixtures_cloudberry import (
    CLOUDBERRY_EMAILS,
    CLOUDBERRY_STATS,
    RC1_JB_MINUS_ONE_ID,
    RC1_JUSTIN_REPLY_ID,
    RC1_VOTE_ID,
    RC2_RESULT_ID,
    RC2_SHUXIN_PLUS_ONE_ID,
    RC2_VOTE_ID,
)


def fake_read_json(url: str) -> dict[str, Any]:
    """Serve the captured archive instead of the network."""
    if "email.lua" in url:
        message_id = url.split("id=", 1)[1].split("&", 1)[0]
        try:
            return CLOUDBERRY_EMAILS[message_id]
        except KeyError:
            return {"error": f"unknown message {message_id}"}
    return CLOUDBERRY_STATS


def summarize(message_id: str) -> dict[str, Any]:
    with mock.patch.object(client, "_read_json", side_effect=fake_read_json):
        return client.summarize_release_vote_thread(message_id=message_id)


def message_by_id(summary: dict[str, Any], message_id: str) -> dict[str, Any]:
    for message in summary["messages"]:
        if message["id"] == message_id:
            return message
    raise AssertionError(f"{message_id} is not in the thread")


def voter_by_name(summary: dict[str, Any], name: str) -> dict[str, Any]:
    matches = [voter for voter in summary["voters"] if name in str(voter["from"])]
    if len(matches) != 1:
        raise AssertionError(f"expected one voter matching {name}, got {len(matches)}")
    return matches[0]


class VoteParsingTests(unittest.TestCase):
    def test_unquoted_body_drops_quotes_and_attribution(self) -> None:
        body = CLOUDBERRY_EMAILS[RC1_JB_MINUS_ONE_ID]["body"]
        own_text = client.unquoted_body(body)

        self.assertTrue(own_text.startswith("-1 (binding)"))
        self.assertNotIn("Hello Incubator Community", own_text)
        self.assertNotIn("wrote:", own_text)

    def test_quoted_vote_is_not_read_as_the_sender_s_own(self) -> None:
        body = (
            "Thanks for checking.\n\n"
            "On Thu, Mar 12, 2026 at 6:42 AM Someone wrote:\n\n"
            "> +1 (binding)\n"
        )
        record = client._vote_record({"body": body}, is_opener=False)

        self.assertIsNone(record["vote"])
        self.assertIsNone(record["declared_binding"])

    def test_version_number_in_subject_is_not_a_vote(self) -> None:
        # "2.1.0-rc1" used to be read as a "0" vote via the subject fallback.
        message = {
            "subject": "Re: [VOTE] Release Apache Cloudberry (Incubating) 2.1.0-rc1",
            "body": "Thanks, I will take a look this week.\n",
        }

        self.assertIsNone(client._vote_record(message, is_opener=False)["vote"])

    def test_declared_binding_reflects_the_voter_s_own_words(self) -> None:
        cases = {
            "-1 (binding), because ...": True,
            "+1 (non-binding)": False,
            "+1(non-binding)": False,
            "+1 binding": True,
            "+1 (not binding)": False,
            "+1": None,
            "+1 (non-binding, Apache Cloudberry PPMC)": False,
        }
        for line, expected in cases.items():
            with self.subTest(line=line):
                record = client._vote_record({"body": line}, is_opener=False)
                self.assertEqual(record["declared_binding"], expected)

    def test_unmarked_plus_one_is_never_counted_as_binding(self) -> None:
        tally = client._vote_tally(
            [{"vote": "+1", "declared_binding": None}, {"vote": "+1", "declared_binding": True}]
        )

        self.assertEqual(tally["plus_one"], 2)
        self.assertEqual(tally["binding_plus_one"], 1)


class Rc1ThreadTests(unittest.TestCase):
    def setUp(self) -> None:
        self.summary = summarize(RC1_VOTE_ID)

    def test_vote_call_is_not_a_vote(self) -> None:
        opener = message_by_id(self.summary, RC1_VOTE_ID)

        self.assertTrue(opener["is_opener"])
        self.assertIsNone(opener["vote"])
        self.assertIsNone(opener["declared_binding"])

    def test_jb_minus_one_is_declared_binding(self) -> None:
        message = message_by_id(self.summary, RC1_JB_MINUS_ONE_ID)

        self.assertEqual(message["vote"], "-1")
        self.assertIs(message["declared_binding"], True)

    def test_discussion_reply_carries_no_vote(self) -> None:
        # Justin's reply is about gradle-wrapper.jar and contains no vote.
        message = message_by_id(self.summary, RC1_JUSTIN_REPLY_ID)

        self.assertIsNone(message["vote"])
        self.assertIsNone(message["declared_binding"])

    def test_one_vote_per_person_the_last_one_counts(self) -> None:
        # JB posted three times in this thread; only his vote stands, once.
        self.assertEqual(len(self.summary["voters"]), 1)
        jb = voter_by_name(self.summary, "Jean-Baptiste")
        self.assertEqual(jb["vote"], "-1")
        self.assertIs(jb["declared_binding"], True)

    def test_tallies_count_the_deduplicated_votes(self) -> None:
        self.assertEqual(
            self.summary["votes"],
            {
                "plus_one": 0,
                "zero": 0,
                "minus_one": 1,
                "binding_plus_one": 0,
                "binding_zero": 0,
                "binding_minus_one": 1,
            },
        )

    def test_thread_is_one_thread_of_many_messages(self) -> None:
        thread = self.summary["thread"]

        self.assertEqual(thread["thread_id"], RC1_VOTE_ID)
        self.assertEqual(thread["message_count"], 7)
        self.assertEqual(self.summary["message_count"], 7)

    def test_other_release_candidates_are_not_pulled_in(self) -> None:
        for message in self.summary["messages"]:
            self.assertIn("2.1.0-rc1", str(message["subject"]))

    def test_result_is_none_when_no_result_was_posted(self) -> None:
        self.assertIsNone(self.summary["result"])


class Rc2ThreadTests(unittest.TestCase):
    def setUp(self) -> None:
        self.summary = summarize(RC2_VOTE_ID)

    def test_shuxin_plus_one_is_declared_non_binding(self) -> None:
        message = message_by_id(self.summary, RC2_SHUXIN_PLUS_ONE_ID)

        self.assertEqual(message["vote"], "+1")
        self.assertIs(message["declared_binding"], False)

    def test_repeat_voter_counted_once(self) -> None:
        shuxin = voter_by_name(self.summary, "Shuxin Pan")

        self.assertEqual(shuxin["vote"], "+1")
        self.assertIs(shuxin["declared_binding"], False)
        self.assertEqual(shuxin["message_id"], RC2_SHUXIN_PLUS_ONE_ID)

    def test_tallies_are_internally_consistent(self) -> None:
        votes = self.summary["votes"]

        self.assertEqual(votes["plus_one"], len(self.summary["voters"]))
        self.assertEqual(votes["plus_one"], 5)
        self.assertEqual(votes["binding_plus_one"], 3)
        self.assertLessEqual(votes["binding_plus_one"], votes["plus_one"])
        self.assertEqual(votes["zero"], 0)
        self.assertEqual(votes["minus_one"], 0)

    def test_result_thread_is_linked(self) -> None:
        result = self.summary["result"]

        self.assertIsNotNone(result)
        self.assertEqual(result["id"], RC2_RESULT_ID)
        self.assertIn("[RESULT]", str(result["subject"]))
        self.assertEqual(result["permalink"], client.permalink(RC2_RESULT_ID))


class ThreadDiscoveryTests(unittest.TestCase):
    def test_replies_group_into_threads_without_a_thread_id(self) -> None:
        with mock.patch.object(client, "_read_json", side_effect=fake_read_json):
            found = client.find_release_vote_threads(podling="cloudberry")

        by_subject = {thread["normalized_subject"]: thread for thread in found["threads"]}
        self.assertEqual(found["count"], 2)
        rc1 = by_subject["[vote] release apache cloudberry (incubating) 2.1.0-rc1"]
        rc2 = by_subject["[vote] release apache cloudberry (incubating) 2.1.0-rc2"]
        self.assertEqual(rc1["thread_id"], RC1_VOTE_ID)
        self.assertEqual(rc1["message_count"], 7)
        self.assertEqual(rc2["thread_id"], RC2_VOTE_ID)
        self.assertEqual(rc2["message_count"], 7)


if __name__ == "__main__":
    unittest.main()
