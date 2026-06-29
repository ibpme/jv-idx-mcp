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

The server supports three authentication modes (checked in this order):

### 1. OAuth 2.0 (recommended for production)

When `OAUTH_ISSUER` is set, the server acts as an OAuth 2.0 Resource Server per the MCP authorization specification. It validates JWT access tokens via the issuer's JWKS endpoint and returns proper `401 Unauthorized` responses with `WWW-Authenticate` headers.

Required environment variables:
- `OAUTH_ISSUER` — OAuth/OIDC issuer URL (e.g. `https://accounts.google.com` or your Auth0/Keycloak domain)

Optional environment variables:
- `OAUTH_JWKS_URI` — JWKS endpoint URI (defaults to `issuer/.well-known/jwks.json`)
- `OAUTH_AUDIENCE` — Expected `aud` claim in tokens
- `OAUTH_SCOPES` — Comma-separated required scopes (default: `mcp:read`)
- `OAUTH_PUBLIC_PATHS` — Comma-separated path patterns that bypass auth

Example:
```bash
export OAUTH_ISSUER=https://your-auth0-domain.us.auth0.com
export OAUTH_AUDIENCE=https://jv-idx-mcp.yourdomain.com
export OAUTH_SCOPES=mcp:read
```

The server exposes OAuth 2.0 Protected Resource Metadata at `/.well-known/oauth-protected-resource` for MCP client discovery.

### 2. Simple Bearer Token

Set `MCP_API_KEY` to enable static Bearer token auth. Unauthenticated requests receive `401`.

```bash
export MCP_API_KEY=$(openssl rand -hex 32)
```

Clients must send `Authorization: Bearer <token>` header. This mode is used when OAuth is not configured.

### 3. No Auth

When neither `OAUTH_ISSUER` nor `MCP_API_KEY` is set, the server runs openly.

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
# Option A: OAuth 2.0 (recommended)
export OAUTH_ISSUER=https://your-auth-domain.com
export OAUTH_AUDIENCE=https://jv-idx-mcp.yourdomain.com
docker compose up -d

# Option B: Simple Bearer token
export MCP_API_KEY=your-secret-token
docker compose up -d
```

Then use `http://localhost:8000/mcp` as the URL. Add the `Authorization` header to client configs if auth is enabled.

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
# With OAuth 2.0:
OAUTH_ISSUER=https://your-auth-domain.com OAUTH_AUDIENCE=https://jv-idx-mcp.yourdomain.com uv run python server.py
# With simple Bearer token:
MCP_API_KEY=your-secret-token uv run python server.py
# Without auth:
uv run python server.py
```
