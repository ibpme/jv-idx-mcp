# jv-idx-mcp

MCP server exposing Indonesia Stock Exchange (IDX) market data as tools — fundamentals, broker flow, company profiles, and technical analysis via TA-Lib.

## Tools

| Tool | Description |
|---|---|
| `get_stock_fundamental` | Financial statements & ratios from IndoPremier (balance sheet, income, ratios) |
| `get_company_profile` | Company profile from idx.co.id |
| `get_broker_name` | Look up firm names for IDX broker codes |
| `get_broker_details` | Full trading summary for IDX brokers |
| `get_broker_summary` | Top buyers/sellers by lot volume over a date range |
| `get_broker_flow` | Non-overlapping broker activity sliced by interval |
| `get_broker_flow_cumulative` | Expanding cumulative broker positions over time |
| `list_indicators` | Browse ~130 TA-Lib indicators with their parameters |
| `compute_indicator` | Compute a single TA indicator (latest value or time series) |
| `get_ta_summary` | Full TA snapshot — ~50 indicators grouped by category |

## Connecting

The server runs over **Streamable HTTP** (`/mcp`) on port **8000**.

### Remote (hosted)

Replace `<host>` with your server URL (e.g. `https://jv-idx-mcp.imanbudip.me`).

#### Claude Code

Add to `~/.claude.json` or project `.mcp.json`:

```json
{
  "mcpServers": {
    "jv-idx-mcp": {
      "type": "http",
      "url": "https://jv-idx-mcp.imanbudip.me/mcp"
    }
  }
}
```

Or via CLI:

```bash
claude mcp add --transport http jv-idx-mcp https://jv-idx-mcp.imanbudip.me/mcp
```

#### OpenAI Codex

Add to your Codex MCP config:

```json
{
  "mcpServers": {
    "jv-idx-mcp": {
      "type": "http",
      "url": "https://jv-idx-mcp.imanbudip.me/mcp"
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
      "url": "https://jv-idx-mcp.imanbudip.me/mcp"
    }
  }
}
```

---

### Local (self-hosted via Docker)

```bash
docker compose up -d
```

Then use `http://localhost:8000/mcp` as the URL in any of the configs above.

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
uv run mcp run server.py --transport streamable-http --host 0.0.0.0 --port 8000
```
