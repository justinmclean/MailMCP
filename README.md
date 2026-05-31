# Apache Incubator Mail MCP

A small stdio MCP server for reading ASF Incubator public mailing lists via
Apache Pony Mail.

Out of the box it queries the IPMC list:

```text
general@incubator.apache.org
```

It can also query a podling's public lists (`dev`, `users`, `commits`). Given
a podling name and a list name, the server resolves the working domain
automatically: it tries `<podling>.apache.org` first and falls back to the
legacy `<podling>.incubator.apache.org` archive when the flat domain has no
data. You can also pass an explicit `domain` to skip the probe.

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

### Incubator general list (default target)

All of these accept optional `list_name` and `domain` overrides; defaults are
`general` and `incubator.apache.org`.

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

### Podling public lists (dev / users / commits)

All podling tools require `podling` and `list_name` (one of `dev`, `users`,
`commits`). The `domain` argument is optional; if omitted it is auto-resolved
(flat `<podling>.apache.org`, falling back to `<podling>.incubator.apache.org`).
Cached entries for non-default lists are written to a per-list subdirectory of
`--cache-dir` so multiple podlings can coexist.

- `resolve_podling_mail_domain`: returns the resolved Pony Mail domain for a podling list
- `podling_mail_overview`: summarizes a podling public list over a time window
- `recent_podling_mail`: lists recent message summaries from a podling public list
- `search_podling_mail`: searches a podling public list
- `get_podling_email`: fetches one full email from a podling public list
- `cache_podling_mail`: caches podling public list message summaries locally
- `list_cached_podling_mail`: lists cached podling public list summaries
- `get_cached_podling_email`: returns one cached podling public list summary
- `cache_podling_mbox`: downloads and caches one monthly mbox for a podling list
- `cache_podling_mboxes`: downloads and caches a range of monthly mboxes for a podling list
- `list_cached_podling_mboxes`: lists cached monthly mboxes for a podling list

## Test

```bash
python3 -m unittest discover -s tests -v
```

PolicyMCP is an independent tool and is not a project of the Apache Software Foundation. Apache and related marks are trademarks of The Apache Software Foundation.
