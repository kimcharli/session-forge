"""SQLModel storage layer — sessions, messages, insights, annotations."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import event
from sqlalchemy.pool import StaticPool
from sqlmodel import Field, Session, SQLModel, create_engine, select

from session_forge.paths import db_path, project_name_from_path


# ── Type aliases ──────────────────────────────────────────────────────────────

type SessionId = str
type ProjectName = str


# ── Models ────────────────────────────────────────────────────────────────────

class SessionRecord(SQLModel, table=True):
    __tablename__ = "sessions"

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    tool: str
    model: str | None = None
    project_name: str = "unknown"
    project_path: str = "unknown"
    correlation_key: str = "unknown:unknown"
    git_branch: str | None = None
    started_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    ended_at: datetime | None = None
    last_seen_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    message_count: int = 0
    total_input_tokens: int = 0
    total_output_tokens: int = 0


class MessageRecord(SQLModel, table=True):
    __tablename__ = "messages"

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    session_id: str = Field(foreign_key="sessions.id")
    turn_index: int
    role: str
    content: str
    input_tokens: int | None = None
    output_tokens: int | None = None
    latency_ms: int | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class InsightRecord(SQLModel, table=True):
    __tablename__ = "insights"

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    session_id: str = Field(foreign_key="sessions.id")
    category: str  # harness | skill | agent | prompt-pattern
    severity: str  # suggestion | warning | improvement
    summary: str
    detail: str
    applied_at: datetime | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class AnnotationRecord(SQLModel, table=True):
    __tablename__ = "annotations"

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    message_id: str = Field(foreign_key="messages.id")
    tag: str
    note: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ── Engine ────────────────────────────────────────────────────────────────────

def get_engine():
    path = db_path()
    engine = create_engine(
        f"sqlite:///{path}",
        echo=False,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def set_wal(conn, _):
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA busy_timeout=5000")

    SQLModel.metadata.create_all(engine)
    return engine


_engine = None


def engine():
    global _engine
    if _engine is None:
        _engine = get_engine()
    return _engine


# ── CRUD ──────────────────────────────────────────────────────────────────────

def upsert_session(
    session_id: SessionId,
    tool: str,
    model: str | None = None,
    project_path: str | None = None,
) -> SessionRecord:
    project_path = project_path or "unknown"
    project_name = project_name_from_path(project_path)
    correlation_key = f"{tool}:{project_name}"
    now = datetime.now(timezone.utc)

    with Session(engine()) as db:
        record = db.get(SessionRecord, session_id)
        if not record:
            record = SessionRecord(
                id=session_id,
                tool=tool,
                model=model,
                project_name=project_name,
                project_path=project_path,
                correlation_key=correlation_key,
                last_seen_at=now,
            )
            db.add(record)
        else:
            record.last_seen_at = now
            if model and not record.model:
                record.model = model
        db.commit()
        db.refresh(record)
        return record


def add_message(
    session_id: SessionId,
    turn_index: int,
    role: str,
    content: str,
    input_tokens: int | None = None,
    output_tokens: int | None = None,
    latency_ms: int | None = None,
) -> MessageRecord:
    with Session(engine()) as db:
        msg = MessageRecord(
            session_id=session_id,
            turn_index=turn_index,
            role=role,
            content=content,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            latency_ms=latency_ms,
        )
        db.add(msg)
        session = db.get(SessionRecord, session_id)
        if session:
            session.message_count += 1
            session.last_seen_at = datetime.now(timezone.utc)
            if input_tokens:
                session.total_input_tokens += input_tokens
            if output_tokens:
                session.total_output_tokens += output_tokens
        db.commit()
        db.refresh(msg)
        return msg


def get_session(session_id: SessionId) -> SessionRecord | None:
    with Session(engine()) as db:
        return db.get(SessionRecord, session_id)


def get_messages(session_id: SessionId) -> list[MessageRecord]:
    with Session(engine()) as db:
        return db.exec(
            select(MessageRecord)
            .where(MessageRecord.session_id == session_id)
            .order_by(MessageRecord.turn_index)
        ).all()


def list_sessions(limit: int = 20, project_name: ProjectName | None = None) -> list[SessionRecord]:
    with Session(engine()) as db:
        q = select(SessionRecord).order_by(SessionRecord.started_at.desc()).limit(limit)
        if project_name:
            q = q.where(SessionRecord.project_name == project_name)
        return db.exec(q).all()


def add_insight(
    session_id: SessionId,
    category: str,
    severity: str,
    summary: str,
    detail: str,
) -> InsightRecord:
    with Session(engine()) as db:
        insight = InsightRecord(
            session_id=session_id,
            category=category,
            severity=severity,
            summary=summary,
            detail=detail,
        )
        db.add(insight)
        db.commit()
        db.refresh(insight)
        return insight
