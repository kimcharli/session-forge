# Implementation Tasks — Service Bring-Up And Port Resolution

Status: DRAFT
Last Updated: 2026-06-08
Owner: @ckim
Tracking: This file is the execution checklist for the service bring-up workstream.

## Goal

Implement robust service orchestration for `proxy`, `mcp_server`, and
`llama-server` with the following guarantees:

- Reuse existing instances only when identity matches expected service behavior.
- Detect and avoid arbitrary processes occupying configured ports.
- Select fallback ports from configured ranges.
- Persist actual runtime ports to a service-port state file under
  `~/.config/session-forge/`.

## Scope

In scope:

- Config schema additions for startup commands and port ranges.
- Service identity verification (not port-only checks).
- Port conflict and fallback logic.
- Runtime service-port state persistence.
- MCP tools and CLI output updates to surface effective runtime ports.
- Unit/integration tests for edge cases.

Out of scope:

- Launchd/systemd integration.
- Cross-host orchestration.
- TLS/auth hardening for local services.

## Task Breakdown (Execution Checklist)

### 1. Config Schema And Defaults

Owner: @ckim
Status: Not Started

- [ ] Add `services.port_ranges` with per-service ranges:
   - [ ] `proxy`
   - [ ] `mcp_server`
   - [ ] `llama`
- [ ] Keep existing single ports as preferred/default start candidates.
- [ ] Add/retain `services.llama_start_cmd` for llama startup.
- [ ] Update config loader and default YAML comments.

Target files:

- `src/session_forge/config.py`
- `specs/config.md`

Definition of done:

- Config loads with backward compatibility when `services.port_ranges` is absent.
- New defaults are written on fresh config creation.

### 2. Runtime Service-Port State File

Owner: @ckim
Status: Not Started

- [ ] Create runtime state file:
   - [ ] Path: `~/.config/session-forge/service-ports.json`
- [ ] Add schema per service:
   - [ ] `service_name`
   - [ ] `pid`
   - [ ] `port`
   - [ ] `started_at`
   - [ ] `cmd_signature`
   - [ ] `health_url`
   - [ ] `service_identity`
- [ ] Implement atomic writes (temp file + rename).
- [ ] Guard concurrent writes (file lock or process lock strategy).

Target files:

- `src/session_forge/paths.py` (path helper)
- `src/session_forge/service_runtime.py` (new helper module)
- `specs/storage-layout.md`

Definition of done:

- Runtime state file is created and updated only after successful health checks.
- Corrupt partial file writes are prevented.

### 3. Service Identity Verification

Owner: @ckim
Status: Not Started

- [ ] Implement identity checks that require all:
   - [ ] Process exists (PID alive).
   - [ ] Command line matches expected signature.
   - [ ] Health endpoint returns expected service marker.
- [ ] Add per-service identity rules:
   - [ ] `proxy`: `/healthz` returns `{status:"ok", service:"proxy"}`
   - [ ] `mcp_server`: `/healthz` returns `{status:"ok", service:"mcp_server"}`
   - [ ] `llama`: `/health` responds successfully and signature matches configured
      llama command profile.

Target files:

- `src/session_forge/service_runtime.py` (new helper module)
- `src/session_forge/proxy/app.py`
- `src/session_forge/mcp_server/server.py`
- `specs/proxy-design.md`

Definition of done:

- Reuse occurs only when identity check passes.
- Port-only occupancy is never treated as valid service ownership.

### 4. Port Conflict And Fallback Selection

Owner: @ckim
Status: Not Started

- [ ] Resolve startup port in this order:
   - [ ] Preferred configured port.
   - [ ] Remaining candidates in configured range.
- [ ] If preferred port is occupied by non-matching process, skip it.
- [ ] On bind race, retry next candidate.
- [ ] Persist actual bound port from running service, not assumed candidate.
- [ ] Return structured error if range is exhausted.

Target files:

- `src/session_forge/service_runtime.py`
- `src/session_forge/mcp_server/server.py`
- `specs/config.md`

Definition of done:

- Steal-port scenario reliably recovers within configured range.
- Exhausted range reports actionable diagnostics.

### 5. MCP Tool Integration

Owner: @ckim
Status: Not Started

- [ ] Extend `service_status` to report:
   - [ ] configured port
   - [ ] effective runtime port
   - [ ] identity validation result
- [ ] Extend `service_up` (or add `ensure_service_up`) to:
   - [ ] verify running instance identity
   - [ ] start service on fallback port if needed
   - [ ] persist runtime port file on success
- [ ] Keep behavior explicit for `proxy` and `mcp_server` if manual start policy is
   retained.

Target files:

- `src/session_forge/mcp_server/server.py`
- `specs/schema.md`
- `specs/proxy-design.md`

Definition of done:

- MCP responses clearly distinguish configured vs effective runtime endpoint.
- Tools return deterministic payloads for automation.

### 6. CLI Surface Updates

Owner: @ckim
Status: Not Started

- [ ] Update `show-paths` to print:
   - [ ] configured ports
   - [ ] active/effective ports from `service-ports.json`
   - [ ] state file location
- [ ] Add clear notes when service is down or identity mismatch is detected.

Target files:

- `src/session_forge/cli.py`
- `README.md`

Definition of done:

- Users can diagnose effective runtime endpoints from a single command.

### 7. Tests

Owner: @ckim
Status: Not Started

- [ ] Add unit tests for service runtime logic:
   - [ ] valid identity reuse
   - [ ] invalid identity on occupied port
   - [ ] fallback range selection
   - [ ] range exhaustion
   - [ ] stale PID record
- [ ] Add integration-style tests for MCP tool behavior:
   - [ ] `service_status` fields and identity flags
   - [ ] `service_up` updates runtime port file
- [ ] Add concurrency test for state-file update locking.

Target files:

- `tests/test_service_runtime.py` (new)
- `tests/test_mcp_service_tools.py` (new)
- existing tests as needed

Definition of done:

- New tests pass consistently.
- Existing suite remains green.

## Delivery Order

1. Config schema + runtime state module
2. Identity checks + fallback port algorithm
3. MCP tool and CLI integration
4. Tests
5. Spec/README final sync

## Acceptance Criteria

- Service reuse is identity-based, not port-based.
- Port-steal cases are handled by fallback port selection.
- Actual runtime ports are persisted in
  `~/.config/session-forge/service-ports.json`.
- MCP and CLI surfaces expose configured and effective runtime ports.
- Test coverage includes steal-port, stale-pid, bind-race, and range-exhaustion
  scenarios.

## Execution Log

- 2026-06-08: Initial task plan created and converted to checklist tracking.
