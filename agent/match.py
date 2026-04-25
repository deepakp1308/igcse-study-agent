"""Deterministic shortlisting for chapter-question matching.

The agent is responsible for the final LLM judgment (``MatchDecision``). This
module just produces a ranked shortlist using local embeddings so the agent
only has to review a small candidate set per chapter.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray
from sqlalchemy import select

from agent.config import MATCH_THRESHOLD_DEFAULT
from agent.embed.local import cosine_matrix, embed_texts
from agent.store.db import Chapter, Question, session_scope


@dataclass
class Candidate:
    question_id: int
    paper_id: int
    number: str
    type: str
    marks: int
    stem: str
    similarity: float


def _chapter_query_text(profile: dict[str, object]) -> str:
    """Flatten a ChapterProfile JSON into a single recall query string."""

    chunks: list[str] = []
    chunks.append(str(profile.get("chapter_name", "")))
    topics = profile.get("syllabus_topics") or []
    if isinstance(topics, list):
        for t in topics:
            if isinstance(t, dict):
                name = t.get("name", "")
                summary = t.get("summary", "")
                key_terms = t.get("key_terms") or []
                chunks.append(f"{name}: {summary}")
                if isinstance(key_terms, list):
                    chunks.append(" ".join(str(k) for k in key_terms))
    defs = profile.get("definitions") or []
    if isinstance(defs, list):
        chunks.append(" ".join(str(d) for d in defs))
    vocab = profile.get("vocabulary") or []
    if isinstance(vocab, list):
        chunks.append(" ".join(str(v) for v in vocab))
    return "\n".join(c for c in chunks if c)


def shortlist_candidates(
    subject: str,
    chapter_name: str,
    top_k: int = 60,
    similarity_floor: float = 0.25,
) -> list[Candidate]:
    """Return top-K questions in the same subject ranked by embedding similarity."""

    with session_scope() as s:
        chapter = s.execute(
            select(Chapter).where(Chapter.subject == subject, Chapter.name == chapter_name)
        ).scalar_one_or_none()
        if chapter is None:
            raise LookupError(f"Chapter not found: {subject}/{chapter_name}")

        query_text = _chapter_query_text(chapter.profile_json)

        questions = list(
            s.execute(select(Question).where(Question.paper.has(subject=subject))).scalars()
        )
        if not questions:
            return []

        stems = [_question_text(q) for q in questions]
        q_matrix: NDArray[np.float32]
        # Use cached embeddings when present
        cached = [q.embedding for q in questions]
        need_compute = [i for i, e in enumerate(cached) if not e]
        if need_compute:
            new_vecs = embed_texts([stems[i] for i in need_compute])
            for local_i, vec in zip(need_compute, new_vecs, strict=True):
                questions[local_i].embedding = vec.tolist()
            s.flush()
        q_matrix = np.stack(
            [np.asarray(q.embedding, dtype=np.float32) for q in questions]
        )

        c_matrix = embed_texts([query_text])
        sims = cosine_matrix(c_matrix, q_matrix)[0]
        ranked = sorted(
            zip(questions, sims.tolist(), strict=True),
            key=lambda pair: pair[1],
            reverse=True,
        )
        out: list[Candidate] = []
        for q, sim in ranked:
            if sim < similarity_floor:
                break
            out.append(
                Candidate(
                    question_id=q.id,
                    paper_id=q.paper_id,
                    number=q.number,
                    type=q.type,
                    marks=q.marks,
                    stem=q.stem,
                    similarity=float(sim),
                )
            )
            if len(out) >= top_k:
                break
        return out


def _question_text(q: Question) -> str:
    """Flatten a Question row into a single recall string."""

    parts = [q.stem]
    for sp in q.sub_parts_json or []:
        if isinstance(sp, dict):
            prompt = sp.get("prompt", "")
            if prompt:
                parts.append(str(prompt))
    return " \n ".join(parts)


def dedup_questions(ids: list[int], cosine_threshold: float) -> list[int]:
    """Return a de-duplicated subset of question ids (greedy, order-preserving)."""

    if not ids:
        return []
    with session_scope() as s:
        rows = list(
            s.execute(select(Question).where(Question.id.in_(ids))).scalars()
        )
    id_to_row = {q.id: q for q in rows}
    ordered = [id_to_row[i] for i in ids if i in id_to_row]
    texts = [_question_text(q) for q in ordered]
    need = [i for i, q in enumerate(ordered) if not q.embedding]
    if need:
        vecs = embed_texts([texts[i] for i in need])
        with session_scope() as s:
            for local_i, vec in zip(need, vecs, strict=True):
                row = s.get(Question, ordered[local_i].id)
                if row is not None:
                    row.embedding = vec.tolist()
    if any(not q.embedding for q in ordered):
        with session_scope() as s:
            refreshed = [s.get(Question, q.id) for q in ordered]
            ordered = [q for q in refreshed if q is not None]
    mat = np.stack(
        [np.asarray(q.embedding or [], dtype=np.float32) for q in ordered]
    )
    kept: list[int] = []
    kept_rows: list[int] = []
    for i, q in enumerate(ordered):
        if not kept_rows:
            kept.append(q.id)
            kept_rows.append(i)
            continue
        keep_mat = mat[kept_rows]
        sims = cosine_matrix(mat[i : i + 1], keep_mat)[0]
        if float(np.max(sims)) < cosine_threshold:
            kept.append(q.id)
            kept_rows.append(i)
    return kept


__all__ = [
    "MATCH_THRESHOLD_DEFAULT",
    "Candidate",
    "dedup_questions",
    "shortlist_candidates",
]
