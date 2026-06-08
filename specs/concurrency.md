# Concurrency — session-forge

## Problem

Two concurrency issues exist in the current implementation:

1. **SQLite write contention** — default SQLite uses a single exclusive write lock.
   With 3 tools firing simultaneously, writes serialize without error but degrade
   under sustained load and can cause `database is locked` errors under bursts.

2. **Sidecar write races** — `write_session_sidecar()` does a full file rewrite on
   every turn. Two turns for the same session arriving within milliseconds will
   interleave writes and corrupt the markdown file.

## SQLite: WAL Mode

### Fix

Enable Write-Ahead Logging (WAL) in `storage.py`:

```python
from sqlalchemy import event

def get_engine():
    ...
    engine = create_engine(f"sqlite:///{db_path}", echo=False)

    @event.listens_for(engine, "connect")
    def set_wal(conn, _):
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")  # safe with WAL
        conn.execute("PRAGMA busy_timeout=5000")   # wait up to 5s on lock

    SQLModel.metadata.create_all(engine)
    return engine
```

### Why

WAL allows concurrent readers and one writer simultaneously. `busy_timeout` prevents
immediate `database is locked` errors under burst writes. `synchronous=NORMAL` is
safe with WAL and faster than the default `FULL`.

### Impact

- No schema changes required
- Backward compatible — existing `sessions.db` files auto-upgrade
- Adds `sessions.db-wal` and `sessions.db-shm` files (already in `.gitignore`)

---

## Sidecar Writes: Per-Session Async Lock

### Problem Detail

`write_session_sidecar()` is called from async context (FastAPI request handler).
Two concurrent ingest requests for the same session both call it, both read the
current file, both rewrite it — last write wins and drops the other turn.

### Fix

Maintain a module-level dict of `asyncio.Lock` objects keyed by `session_id`:

```python
# sidecar.py
import asyncio
from collections import defaultdict

_session_locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)

async def write_session_sidecar_safe(session_id: str, ...) -> Path:
    async with _session_locks[session_id]:
        return write_session_sidecar(session_id, ...)
```

### Implementation Contract

- Rename current `write_session_sidecar()` → `_write_session_sidecar_sync()` (internal)
- Expose `write_session_sidecar_safe()` as the public async API
- `mcp_server/server.py` must `await write_session_sidecar_safe(...)` instead of
  calling the sync version directly
- Lock dict is process-local (fine — single process per MCP server instance)
- Locks are never explicitly cleaned up (negligible memory: one `Lock` per seen session)

---

## Connection Pool: Limit SQLite Writers

SQLModel/SQLAlchemy defaults to a connection pool. For SQLite, multiple pooled
connections can cause contention. Set pool to `StaticPool` or `NullPool` for SQLite:

```python
from sqlalchemy.pool import StaticPool

engine = create_engine(
    f"sqlite:///{db_path}",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
```

`StaticPool` uses a single shared connection — safe for SQLite, eliminates all
lock contention at the pool level. WAL mode still handles concurrent readers.

---

## Summary of Changes Required

| File | Change |
|---|---|
| `mcp_server/storage.py` | Add WAL pragma, `busy_timeout`, `StaticPool` |
| `mcp_server/sidecar.py` | Add `_session_locks` dict, expose async-safe writer |
| `mcp_server/server.py` | Await `write_session_sidecar_safe()` instead of sync call |

## Not Required

- No schema changes
- No changes to proxy or analyzer
- No external dependencies (all stdlib/SQLAlchemy)
