from __future__ import annotations

from pathlib import Path
import sys
import unittest
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
        self.assertEqual(
            tools.TOOLS["get_incubator_general_email"]["inputSchema"]["properties"]["message_id"][
                "type"
            ],
            "string",
        )


if __name__ == "__main__":
    unittest.main()
