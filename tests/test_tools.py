from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from apache_incubator_mail_mcp import client, tools
from tests.fixtures import SAMPLE_STATS


class ToolsTests(unittest.TestCase):
    def test_search_uses_required_query(self) -> None:
        with mock.patch.object(client, "_read_json", return_value=SAMPLE_STATS):
            result = tools.search_incubator_general_mail("proposal", limit=1)

        self.assertEqual(result["query"], "proposal")
        self.assertEqual(len(result["emails"]), 1)

    def test_overview_moves_emails_to_sample(self) -> None:
        with mock.patch.object(client, "_read_json", return_value=SAMPLE_STATS):
            result = tools.incubator_general_mail_overview(limit=1)

        self.assertIn("sample", result)
        self.assertNotIn("emails", result)

    def test_tools_registered_with_schemas(self) -> None:
        self.assertIn("search_incubator_general_mail", tools.TOOLS)
        self.assertIn("cache_incubator_general_mbox", tools.TOOLS)
        self.assertIn("find_release_vote_threads", tools.TOOLS)
        self.assertIn("podling_release_vote_history", tools.TOOLS)
        self.assertEqual(
            tools.TOOLS["get_incubator_general_email"]["inputSchema"]["properties"]["message_id"][
                "type"
            ],
            "string",
        )
        self.assertEqual(
            tools.TOOLS["summarize_release_vote_thread"]["inputSchema"]["properties"][
                "message_id"
            ]["type"],
            "string",
        )

    def test_podling_tools_registered(self) -> None:
        expected = {
            "resolve_podling_mail_domain",
            "podling_mail_overview",
            "recent_podling_mail",
            "search_podling_mail",
            "get_podling_email",
            "cache_podling_mail",
            "list_cached_podling_mail",
            "get_cached_podling_email",
            "cache_podling_mbox",
            "cache_podling_mboxes",
            "list_cached_podling_mboxes",
        }
        self.assertTrue(expected.issubset(tools.TOOLS.keys()))

    def test_podling_mail_overview_targets_resolved_domain(self) -> None:
        captured: list[str] = []

        def fake_read_json(url: str) -> dict:
            captured.append(url)
            # The flat domain probe returns empty; the legacy subdomain probe
            # (and any subsequent data fetch against it) returns sample data.
            if "domain=iceberg.apache.org" in url:
                return {"hits": 0, "firstYear": None, "lastYear": None, "emails": []}
            return {**SAMPLE_STATS, "list": "dev@iceberg.incubator.apache.org"}

        with mock.patch.object(client, "_read_json", side_effect=fake_read_json):
            result = tools.podling_mail_overview(
                podling="Iceberg", list_name="dev", limit=1
            )

        self.assertEqual(result["podling"], "iceberg")
        self.assertEqual(result["list"], "dev@iceberg.incubator.apache.org")
        # The data-fetching call should target the legacy subdomain.
        data_url = captured[-1]
        self.assertIn("list=dev", data_url)
        self.assertIn("domain=iceberg.incubator.apache.org", data_url)

    def test_podling_tools_require_known_list_name(self) -> None:
        with self.assertRaises(ValueError):
            tools.podling_mail_overview(podling="iceberg", list_name="private")

    def test_resolve_podling_mail_domain_tool(self) -> None:
        with mock.patch.object(
            client,
            "_read_json",
            return_value={"hits": 1, "firstYear": 2024, "lastYear": 2024, "emails": []},
        ):
            result = tools.resolve_podling_mail_domain(podling="pekko", list_name="dev")
        self.assertEqual(result["domain"], "pekko.apache.org")
        self.assertEqual(result["list"], "dev@pekko.apache.org")
        self.assertEqual(
            result["candidates"],
            ["pekko.apache.org", "pekko.incubator.apache.org"],
        )

    def test_general_tools_accept_list_overrides(self) -> None:
        # Schema must expose the new optional knobs on the existing tools.
        schema = tools.TOOLS["recent_incubator_general_mail"]["inputSchema"]
        self.assertIn("list_name", schema["properties"])
        self.assertIn("domain", schema["properties"])


if __name__ == "__main__":
    unittest.main()
