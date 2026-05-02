from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from apache_incubator_mail_mcp import protocol


class ProtocolTests(unittest.TestCase):
    def test_initialize(self) -> None:
        response = protocol.handle_payload({"jsonrpc": "2.0", "id": 1, "method": "initialize"})

        assert isinstance(response, dict)
        self.assertEqual(response["result"]["serverInfo"]["name"], "apache-incubator-mail-mcp")

    def test_tools_list_includes_search_tool(self) -> None:
        response = protocol.handle_payload({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        assert isinstance(response, dict)
        names = {tool["name"] for tool in response["result"]["tools"]}

        self.assertIn("search_incubator_general_mail", names)
        self.assertIn("cache_incubator_general_mboxes", names)
        self.assertIn("find_release_vote_threads", names)
        self.assertIn("summarize_release_vote_thread", names)

    def test_rejects_unknown_tool_argument(self) -> None:
        response = protocol.handle_payload(
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {
                    "name": "recent_incubator_general_mail",
                    "arguments": {"unexpected": True},
                },
            }
        )

        assert isinstance(response, dict)
        self.assertEqual(response["error"]["code"], -32602)


if __name__ == "__main__":
    unittest.main()
