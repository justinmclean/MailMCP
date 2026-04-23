# Apache Incubator Mail MCP

A small stdio MCP server for reading the ASF Incubator public general mailing list.

By default, it queries Apache Pony Mail for:

```text
general@incubator.apache.org
```

The default API base is:

```text
https://lists.apache.org/api
```

## Install

```bash
python3 -m pip install .
```

For development:

```bash
python3 -m pip install -e .[dev]
```

## Run

```bash
incubator-mail-mcp --cache-dir /path/to/cache
```

For local development without installing:

```bash
python3 server.py --cache-dir /path/to/cache
```

The server uses `stdio`, so it is intended to be launched by an MCP client.

## Example MCP Client Config

```json
{
  "mcpServers": {
    "incubator-mail": {
      "command": "incubator-mail-mcp",
      "args": [
        "--cache-dir",
        "/path/to/cache"
      ]
    }
  }
}
```

## Tools

- `incubator_general_mail_overview`: summarizes mail matching a time window and optional query
- `recent_incubator_general_mail`: lists recent message summaries
- `search_incubator_general_mail`: searches the general list
- `get_incubator_general_email`: fetches one full email by Pony Mail id or Message-ID
- `cache_incubator_general_mail`: writes matching message summaries to the local cache
- `list_cached_incubator_general_mail`: lists cached message summaries
- `get_cached_incubator_general_email`: returns one cached message summary
- `cache_incubator_general_mbox`: downloads and caches one monthly raw mbox
- `cache_incubator_general_mboxes`: downloads and caches a range of monthly raw mboxes
- `list_cached_incubator_general_mboxes`: lists cached raw mbox files
- `find_release_vote_threads`: finds likely Incubator podling release vote threads
- `find_release_result_threads`: finds likely release vote result threads
- `summarize_release_vote_thread`: summarizes likely votes and result messages in one release vote thread
- `podling_release_vote_history`: returns likely release vote and result history for one podling

## Test

```bash
python3 -m unittest discover -s tests -v
```
