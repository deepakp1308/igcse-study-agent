"""Review-queue operations (add/list/resolve)."""

from __future__ import annotations

from sqlalchemy import select

from agent.store.db import ReviewItem, session_scope


def add_review(kind: str, ref: str, reason: str, raw: str = "") -> int:
    with session_scope() as s:
        item = ReviewItem(kind=kind, ref=ref, reason=reason, raw=raw)
        s.add(item)
        s.flush()
        return item.id


def list_pending() -> list[ReviewItem]:
    with session_scope() as s:
        return list(
            s.execute(select(ReviewItem).where(~ReviewItem.resolved).order_by(ReviewItem.id)).scalars()
        )


def resolve(item_id: int) -> bool:
    with session_scope() as s:
        item = s.get(ReviewItem, item_id)
        if item is None:
            return False
        item.resolved = True
        return True
