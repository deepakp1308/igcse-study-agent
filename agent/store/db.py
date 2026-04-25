"""SQLAlchemy ORM + session/engine factory.

Single-file schema. ``init_db()`` is idempotent and creates tables on demand;
this is sufficient for a local cache. If the schema ever changes incompatibly
the user simply deletes ``agent/db.sqlite`` and re-ingests.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import (
    JSON,
    Boolean,
    Float,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    create_engine,
)
from sqlalchemy.engine import Engine
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    Session,
    mapped_column,
    relationship,
    sessionmaker,
)

from agent.config import db_path


class Base(DeclarativeBase):
    pass


class Paper(Base):
    __tablename__ = "papers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    subject: Mapped[str] = mapped_column(String, index=True)
    year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    session: Mapped[str | None] = mapped_column(String, nullable=True)
    paper_number: Mapped[str | None] = mapped_column(String, nullable=True)
    tier: Mapped[str] = mapped_column(String, default="unknown")
    total_marks: Mapped[int | None] = mapped_column(Integer, nullable=True)
    path: Mapped[str] = mapped_column(String, unique=True)
    hash: Mapped[str] = mapped_column(String, unique=True, index=True)
    metadata_confidence: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(UTC))

    pages: Mapped[list[Page]] = relationship(back_populates="paper", cascade="all, delete-orphan")
    questions: Mapped[list[Question]] = relationship(
        back_populates="paper", cascade="all, delete-orphan"
    )


class Page(Base):
    __tablename__ = "pages"
    __table_args__ = (UniqueConstraint("paper_id", "idx", name="uq_pages_paper_idx"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    paper_id: Mapped[int] = mapped_column(ForeignKey("papers.id"), index=True)
    idx: Mapped[int] = mapped_column(Integer)
    png_path: Mapped[str] = mapped_column(String)

    paper: Mapped[Paper] = relationship(back_populates="pages")


class Question(Base):
    __tablename__ = "questions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    paper_id: Mapped[int] = mapped_column(ForeignKey("papers.id"), index=True)
    page_id: Mapped[int | None] = mapped_column(ForeignKey("pages.id"), nullable=True, index=True)
    number: Mapped[str] = mapped_column(String)
    type: Mapped[str] = mapped_column(String)
    marks: Mapped[int] = mapped_column(Integer, default=0)
    stem: Mapped[str] = mapped_column(String)
    sub_parts_json: Mapped[list[dict[str, object]]] = mapped_column(JSON, default=list)
    options_json: Mapped[list[dict[str, object]] | None] = mapped_column(JSON, nullable=True)
    figure_paths_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    figure_bboxes_json: Mapped[list[dict[str, float]]] = mapped_column(JSON, default=list)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    notes: Mapped[str | None] = mapped_column(String, nullable=True)
    embedding: Mapped[list[float] | None] = mapped_column(JSON, nullable=True)

    paper: Mapped[Paper] = relationship(back_populates="questions")


class Chapter(Base):
    __tablename__ = "chapters"
    __table_args__ = (UniqueConstraint("subject", "name", name="uq_chapters_subject_name"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    subject: Mapped[str] = mapped_column(String, index=True)
    name: Mapped[str] = mapped_column(String, index=True)
    profile_json: Mapped[dict[str, object]] = mapped_column(JSON)
    screenshot_paths_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    priming_json: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True)
    primed_at: Mapped[datetime | None] = mapped_column(nullable=True)


class Match(Base):
    __tablename__ = "matches"

    chapter_id: Mapped[int] = mapped_column(ForeignKey("chapters.id"), primary_key=True)
    question_id: Mapped[int] = mapped_column(ForeignKey("questions.id"), primary_key=True)
    score: Mapped[float] = mapped_column(Float, default=0.0)
    fit: Mapped[str] = mapped_column(String, default="none")
    rationale: Mapped[str] = mapped_column(String, default="")
    missing_concepts_json: Mapped[list[str]] = mapped_column(JSON, default=list)


class Solution(Base):
    __tablename__ = "solutions"

    question_id: Mapped[int] = mapped_column(ForeignKey("questions.id"), primary_key=True)
    chapter_id: Mapped[int] = mapped_column(ForeignKey("chapters.id"), primary_key=True)
    solver_json: Mapped[dict[str, object]] = mapped_column(JSON)
    critic_json: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True)
    reconciled_json: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True)
    out_of_scope: Mapped[bool] = mapped_column(Boolean, default=False)
    critic_agrees: Mapped[bool] = mapped_column(Boolean, default=True)
    judge_json: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True)
    judge_quality_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    iteration_count: Mapped[int] = mapped_column(Integer, default=1)
    final_quality_score: Mapped[float | None] = mapped_column(Float, nullable=True)


class ExtractionAuditRow(Base):
    """One audit row per (paper, page, iteration). Multiple iterations allowed
    so we can re-audit after appending missed questions."""

    __tablename__ = "extraction_audits"

    paper_id: Mapped[int] = mapped_column(ForeignKey("papers.id"), primary_key=True)
    page_idx: Mapped[int] = mapped_column(Integer, primary_key=True)
    iteration: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    audit_json: Mapped[dict[str, object]] = mapped_column(JSON)
    complete: Mapped[bool] = mapped_column(Boolean, default=False)
    completed_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(UTC))


class Rubric(Base):
    __tablename__ = "rubrics"

    question_id: Mapped[int] = mapped_column(ForeignKey("questions.id"), primary_key=True)
    chapter_id: Mapped[int] = mapped_column(ForeignKey("chapters.id"), primary_key=True)
    rubric_json: Mapped[dict[str, object]] = mapped_column(JSON)


class ReviewItem(Base):
    __tablename__ = "review_queue"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    kind: Mapped[str] = mapped_column(String)
    ref: Mapped[str] = mapped_column(String)
    reason: Mapped[str] = mapped_column(String)
    raw: Mapped[str] = mapped_column(String, default="")
    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(UTC))
    resolved: Mapped[bool] = mapped_column(Boolean, default=False)


_engine: Engine | None = None
_Session: sessionmaker[Session] | None = None


def _engine_for(path: Path) -> Engine:
    path.parent.mkdir(parents=True, exist_ok=True)
    return create_engine(f"sqlite:///{path}", future=True)


_MIGRATIONS: list[tuple[str, str, str]] = [
    # (table, column, ddl_type) - additive only.
    ("chapters", "priming_json", "JSON"),
    ("chapters", "primed_at", "DATETIME"),
    ("solutions", "judge_json", "JSON"),
    ("solutions", "judge_quality_score", "FLOAT"),
    ("solutions", "iteration_count", "INTEGER DEFAULT 1"),
    ("solutions", "final_quality_score", "FLOAT"),
    ("questions", "figure_bboxes_json", "JSON DEFAULT '[]'"),
]


def _ensure_columns(engine: Engine) -> None:
    """Idempotently ALTER TABLE for new columns added after the DB was created.

    SQLAlchemy's create_all only creates new tables; it does not migrate
    existing tables, so we add missing columns here. Order matters only for
    foreign keys, and these are all simple additive nullable columns.
    """
    from sqlalchemy import inspect, text

    insp = inspect(engine)
    for table, column, ddl in _MIGRATIONS:
        if table not in insp.get_table_names():
            continue
        cols = {c["name"] for c in insp.get_columns(table)}
        if column in cols:
            continue
        with engine.begin() as conn:
            conn.execute(text(f'ALTER TABLE "{table}" ADD COLUMN "{column}" {ddl}'))


def init_db(path: Path | None = None) -> Engine:
    """Create (or open) the SQLite DB and ensure all tables + columns exist."""

    global _engine, _Session
    target = path or db_path()
    _engine = _engine_for(target)
    Base.metadata.create_all(_engine)
    _ensure_columns(_engine)
    _Session = sessionmaker(bind=_engine, expire_on_commit=False, future=True)
    return _engine


@contextmanager
def session_scope() -> Iterator[Session]:
    if _Session is None:
        init_db()
    assert _Session is not None
    session = _Session()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
