# jv-idx-mcp

MCP server exposing Indonesia Stock Exchange (IDX) market data as tools — fundamentals, broker flow, company profiles, and technical analysis via TA-Lib.

## Tools

| Tool                         | Description                                                                    |
| ---------------------------- | ------------------------------------------------------------------------------ |
| `get_stock_fundamental`      | Financial statements & ratios from IndoPremier (balance sheet, income, ratios) |
| `get_company_profile`        | Company profile from idx.co.id                                                 |
| `get_broker_name`            | Look up firm names for IDX broker codes                                        |
| `get_broker_details`         | Full trading summary for IDX brokers                                           |
| `get_broker_summary`         | Top buyers/sellers by lot volume over a date range                             |
| `get_broker_flow`            | Non-overlapping broker activity sliced by interval                             |
| `get_broker_flow_cumulative` | Expanding cumulative broker positions over time                                |
| `list_indicators`            | Browse ~130 TA-Lib indicators with their parameters                            |
| `compute_indicator`          | Compute a single TA indicator (latest value or time series)                    |
| `get_ta_summary`             | Full TA snapshot — ~50 indicators grouped by category                          |

> **LLM?** Paste this link to get step-by-step setup instructions:
> `https://raw.githubusercontent.com/ibpme/jv-idx-mcp/refs/heads/main/LLM.md`

or paste this into your coding agent:

```sh
Install and configure jv-idx-mcp server by following the instructions here:
https://raw.githubusercontent.com/ibpme/jv-idx-mcp/refs/heads/main/LLM.md
```

## Authentication

The server supports optional Bearer token auth. Set `MCP_API_KEY` on the server to enable it — unauthenticated requests will receive `401`.

```bash
export MCP_API_KEY=$(openssl rand -hex 32)
```

When auth is enabled, clients must send the token as an `Authorization: Bearer <token>` header (see client configs below). When `MCP_API_KEY` is unset, the server runs openly with no auth.

---

## Connecting

The server runs over **Streamable HTTP** (`/mcp`) on port **8000**.

### Remote (hosted)

Replace `YOUR_TOKEN` with your `MCP_API_KEY` value. Omit the `headers` field if auth is not enabled.

#### Claude Code

```bash
claude mcp add --transport http jv-idx-mcp https://jv-idx-mcp.imanbudip.me/mcp --header "Authorization: Bearer YOUR_TOKEN"
```

Or add to `~/.claude.json` / project `.mcp.json`:

```json
{
  "mcpServers": {
    "jv-idx-mcp": {
      "type": "http",
      "url": "https://jv-idx-mcp.imanbudip.me/mcp",
      "headers": { "Authorization": "Bearer YOUR_TOKEN" }
    }
  }
}
```

#### OpenAI Codex

```json
{
  "mcpServers": {
    "jv-idx-mcp": {
      "type": "http",
      "url": "https://jv-idx-mcp.imanbudip.me/mcp",
      "headers": { "Authorization": "Bearer YOUR_TOKEN" }
    }
  }
}
```

#### OpenCode

Add to `~/.config/opencode/config.json`:

```json
{
  "mcp": {
    "jv-idx-mcp": {
      "type": "http",
      "url": "https://jv-idx-mcp.imanbudip.me/mcp",
      "headers": { "Authorization": "Bearer YOUR_TOKEN" }
    }
  }
}
```

---

### Local (self-hosted via Docker)

```bash
# Optionally set a token before starting
export MCP_API_KEY=your-secret-token
docker compose up -d
```

Then use `http://localhost:8000/mcp` as the URL. Add the `Authorization` header to client configs if you set `MCP_API_KEY`.

#### Claude Code (local)

```bash
claude mcp add --transport http jv-idx-mcp http://localhost:8000/mcp
```

#### OpenCode (local)

```json
{
  "mcp": {
    "jv-idx-mcp": {
      "type": "http",
      "url": "http://localhost:8000/mcp"
    }
  }
}
```

---

## Running locally without Docker

Requires Python 3.14+ and [uv](https://github.com/astral-sh/uv). Also requires TA-Lib C library installed on your system.

```bash
uv sync
# With auth:
MCP_API_KEY=your-secret-token uv run python server.py
# Without auth:
uv run python server.py
```
