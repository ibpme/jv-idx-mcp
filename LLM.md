# jv-idx-mcp — LLM Setup Guide

You are helping a user add the jv-idx-mcp MCP server to their AI coding tool.
Follow the steps for their tool below. No extra explanation needed — just run the commands or write the config.

## Server info

- Protocol: Streamable HTTP
- Endpoint: https://jv-idx-mcp.imanbudip.me/mcp
- No authentication required

## Claude Code

Run this command:

```bash
claude mcp add --transport http jv-idx-mcp https://jv-idx-mcp.imanbudip.me/mcp
```

To verify:

```bash
claude mcp list
```

## OpenAI Codex

Add this to your MCP config file (typically `codex_mcp_config.json` or wherever Codex reads MCP servers):

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

## OpenCode

Add this block inside `~/.config/opencode/config.json` under the `mcp` key:

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

## Available tools

Once connected, these tools are available:

- `get_stock_fundamental(code, quarter?, output?)` — financial statements & ratios
- `get_company_profile(code)` — company profile from idx.co.id
- `get_broker_name(codes)` — firm names for IDX broker codes
- `get_broker_details(codes)` — full trading summary for brokers
- `get_broker_summary(code, start, end, fd?, board?)` — top buyers/sellers over a date range
- `get_broker_flow(code, lookback_days?, interval_days?, end?, fd?, board?)` — non-overlapping broker activity slices
- `get_broker_flow_cumulative(code, lookback_days?, interval_days?, end?, fd?, board?)` — cumulative broker positions over time
- `list_indicators(group?, search?)` — browse ~130 TA-Lib indicators
- `compute_indicator(code, indicator, params?, period?, interval?, start?, end?, series?, last_n?)` — compute a single TA indicator
- `get_ta_summary(code, period?, interval?, start?, end?, output?)` — full TA snapshot (~50 indicators)

All `code` arguments are IDX ticker symbols, e.g. `"BBCA"`, `"TLKM"`, `"GOTO"`.
