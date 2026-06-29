# jv-idx-mcp — LLM Setup Guide

You are helping a user add the jv-idx-mcp MCP server to their AI coding tool.

**Before doing anything else, ask the user two questions using your platform's question/clarification tool:**

1. **Deployment**: Are they connecting to the hosted remote server, or running it locally (Docker or bare Python)?
2. **Authentication**: Is a Bearer token required? (It is required if `MCP_API_KEY` was set when the server was started.) If yes, ask them to provide the token value.

Use the appropriate tool for your platform:
- **Claude Code / Claude Desktop**: use the `AskUserQuestion` tool with both questions in a single call (two questions, each with options).
- **OpenCode / other MCP clients**: ask the questions as a plain conversational message if no structured question tool is available.

Once you have their answers, follow only the matching section below. Do not show sections that don't apply.

---

## Server info

- Protocol: Streamable HTTP (`/mcp`)
- Remote endpoint: `https://jv-idx-mcp.imanbudip.me/mcp`
- Local endpoint: `http://localhost:8000/mcp`
- Auth: Bearer token via `Authorization: Bearer <token>` header (optional — only needed if server was started with `MCP_API_KEY` set)

---

## Setup: Remote + No Auth

### Claude Code
```bash
claude mcp add --transport http jv-idx-mcp https://jv-idx-mcp.imanbudip.me/mcp
```

### OpenAI Codex
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

### OpenCode — `~/.config/opencode/config.json`
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

## Setup: Remote + Bearer Token

Replace `YOUR_TOKEN` with the token the user provided.

### Claude Code
```bash
claude mcp add --transport http jv-idx-mcp https://jv-idx-mcp.imanbudip.me/mcp --header "Authorization: Bearer YOUR_TOKEN"
```

### OpenAI Codex
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

### OpenCode — `~/.config/opencode/config.json`
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

## Setup: Local + No Auth

First, start the server:

**Docker:**
```bash
docker compose up -d
```

**Bare Python (requires Python 3.14+ and [uv](https://github.com/astral-sh/uv)):**
```bash
uv sync
uv run python server.py
```

Then connect:

### Claude Code
```bash
claude mcp add --transport http jv-idx-mcp http://localhost:8000/mcp
```

### OpenAI Codex
```json
{
  "mcpServers": {
    "jv-idx-mcp": {
      "type": "http",
      "url": "http://localhost:8000/mcp"
    }
  }
}
```

### OpenCode — `~/.config/opencode/config.json`
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

## Setup: Local + Bearer Token

Replace `YOUR_TOKEN` with the token the user provided.

First, start the server with the token set:

**Docker:**
```bash
export MCP_API_KEY=YOUR_TOKEN
docker compose up -d
```

**Bare Python:**
```bash
uv sync
MCP_API_KEY=YOUR_TOKEN uv run python server.py
```

Then connect:

### Claude Code
```bash
claude mcp add --transport http jv-idx-mcp http://localhost:8000/mcp --header "Authorization: Bearer YOUR_TOKEN"
```

### OpenAI Codex
```json
{
  "mcpServers": {
    "jv-idx-mcp": {
      "type": "http",
      "url": "http://localhost:8000/mcp",
      "headers": { "Authorization": "Bearer YOUR_TOKEN" }
    }
  }
}
```

### OpenCode — `~/.config/opencode/config.json`
```json
{
  "mcp": {
    "jv-idx-mcp": {
      "type": "http",
      "url": "http://localhost:8000/mcp",
      "headers": { "Authorization": "Bearer YOUR_TOKEN" }
    }
  }
}
```

---

## Verify connection

### Claude Code
```bash
claude mcp list
```

---

## Available tools

| Tool | Description |
|------|-------------|
| `get_stock_fundamental(code, quarter?, output?)` | Financial statements & ratios |
| `get_company_profile(code)` | Company profile from idx.co.id |
| `get_broker_name(codes)` | Firm names for IDX broker codes |
| `get_broker_details(codes)` | Full trading summary for brokers |
| `get_broker_summary(code, start, end, fd?, board?)` | Top buyers/sellers over a date range |
| `get_broker_flow(code, lookback_days?, interval_days?, end?, fd?, board?)` | Non-overlapping broker activity slices |
| `get_broker_flow_cumulative(code, lookback_days?, interval_days?, end?, fd?, board?)` | Cumulative broker positions over time |
| `list_indicators(group?, search?)` | Browse ~130 TA-Lib indicators |
| `compute_indicator(code, indicator, params?, ...)` | Compute a single TA indicator |
| `get_ta_summary(code, period?, interval?, ...)` | Full TA snapshot (~50 indicators) |

All `code` arguments are IDX ticker symbols, e.g. `"BBCA"`, `"TLKM"`, `"GOTO"`.
