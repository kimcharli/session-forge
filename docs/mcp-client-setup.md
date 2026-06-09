# MCP Client Setup — session-forge

How to point Claude Code, Gemini CLI, and GitHub Copilot at the session-forge
MCP server so they can call `service_status` and `service_up`.

**Prerequisite:** `session-forge mcp-server` starts/reuses all managed daemons
before the client connects. The preferred MCP address is
`http://127.0.0.1:8000` (configurable in `~/.config/session-forge/config.yaml`).

Important: treat `8000` as the preferred default, not a guaranteed fixed port.
When that port is occupied by a non-matching process, session-forge can select
an alternate port from the configured range.

Use either of these to discover the effective runtime port:

- `uv run session-forge show-paths`
- `~/.config/session-forge/service-ports.json` (`mcp_server.port`)

---

## Claude Code

**Official docs:** <https://code.claude.com/docs/en/mcp>

**Config file:** `~/.claude.json` (user scope) or `.mcp.json` (project scope)

```json
{
  "mcpServers": {
    "session-forge": {
      "type": "http",
      "url": "http://127.0.0.1:8000"
    }
  }
}
```

Or add via CLI (user scope — available in all projects):

```bash
claude mcp add --transport http session-forge http://127.0.0.1:8000 --scope user
```

Verify: run `/mcp` inside Claude Code — `service_status` and `service_up` tools
should appear under `session-forge`.

---

## Gemini CLI

**Official docs:** <https://github.com/google-gemini/gemini-cli/blob/main/docs/tools/mcp-server.md>

**Config file:** `~/.gemini/settings.json` (user) or `.gemini/settings.json` (project)

```json
{
  "mcpServers": {
    "session-forge": {
      "httpUrl": "http://127.0.0.1:8000"
    }
  }
}
```

> Note: Gemini CLI uses `httpUrl` (not `url`) for the HTTP streamable transport.

Or add via CLI:

```bash
gemini mcp add --transport http session-forge http://127.0.0.1:8000 --scope user
```

Verify: run `/mcp` inside a Gemini CLI session.

---

## GitHub Copilot (VS Code)

**Official docs:** <https://code.visualstudio.com/docs/copilot/chat/mcp-servers>

**Config file:** `.vscode/mcp.json` (workspace, shareable via git) or user profile `mcp.json`

```json
{
  "servers": {
    "session-forge": {
      "type": "http",
      "url": "http://127.0.0.1:8000"
    }
  }
}
```

Or: Command Palette → **MCP: Add Server** → HTTP → paste `http://127.0.0.1:8000`.

Verify: tools appear in Copilot Chat or in the **MCP SERVERS - INSTALLED** panel
in the Extensions view.

---

## Quick comparison

| | Claude Code | Gemini CLI | Copilot / VS Code |
|---|---|---|---|
| HTTP key | `"type": "http"` | `"httpUrl"` | `"type": "http"` |
| Config file | `.mcp.json` / `~/.claude.json` | `settings.json` | `.vscode/mcp.json` |
| Scope flag | `--scope user` | `--scope user` | workspace vs. user profile |
| Verify | `/mcp` | `/mcp` | Extensions → MCP SERVERS |

---

## Available MCP tools

Once connected, the following tools are exposed by the session-forge MCP server:

| Tool | Description |
|---|---|
| `service_status` | Pings proxy, mcp_server, and llama — returns `"up"` or `"down"` for each |
| `service_up("llama")` | Starts llama-server if down, using `services.llama_start_cmd` from config.yaml |
| `list_sessions` | Lists recent stored sessions (filterable by project) |
| `get_session` | Returns full session detail by ID |
| `trigger_analysis` | Queues a session for llama.cpp analysis |

---

## Typical startup workflow

```
# 1. Start/reuse all service daemons (llama, proxy, mcp_server)
uv run session-forge mcp-server

# 2. Verify daemon status
uv run session-forge services status

# 3. From inside Claude Code / Gemini CLI / Copilot, ask:
#    "Call service_status"
#    → if llama is down: "Call service_up with service=llama"
```

To stop everything:

```bash
uv run session-forge services stop
```
