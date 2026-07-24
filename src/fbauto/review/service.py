"""Review gate service: xem / sửa / duyệt / từ chối bài, ghi AuditLog mỗi hành động.

Đây là nền của "review chuyên nghiệp": chỉ người duyệt mới đổi trạng thái bài (mặc định).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, joinedload

from ..db import session_scope
from ..enums import Platform, PostStatus
from ..models import AuditLog, Post, Schedule

# Trạng thái được phép duyệt/sửa (chưa ra ngoài)
_EDITABLE = {PostStatus.DRAFT, PostStatus.NEEDS_REVIEW, PostStatus.REJECTED}
EDITABLE_STATUS_VALUES = frozenset(s.value for s in _EDITABLE)


def is_editable_status(status: str) -> bool:
    return status in EDITABLE_STATUS_VALUES


@dataclass
class PostSummary:
    id: int
    platform: str
    language: str
    status: str
    hook: str | None
    needs_attention: bool
    created_at: datetime
    published_at: datetime | None = None
    topic_id: int | None = None
    topic_title: str | None = None
    score: int | None = None
    scheduled_at: datetime | None = None


def _audit(session: Session, action: str, entity_id: int,
           detail: dict[str, Any] | None = None, actor: str = "human") -> None:
    session.add(
        AuditLog(actor=actor, action=action, entity="post", entity_id=entity_id, detail=detail)
    )


def _to_summary(p: Post, *, topic_title: str | None = None,
                scheduled_at: datetime | None = None) -> PostSummary:
    return PostSummary(
        id=p.id, platform=p.platform.value, language=p.language.value, status=p.status.value,
        hook=p.hook, needs_attention=bool(p.review_note), created_at=p.created_at,
        published_at=p.published_at, topic_id=p.topic_id, topic_title=topic_title,
        score=p.score, scheduled_at=scheduled_at,
    )


def _filtered_posts_stmt(status: PostStatus | None, platform: Platform | None, q: str | None):
    stmt = select(Post)
    if status is not None:
        stmt = stmt.where(Post.status == status)
    if platform is not None:
        stmt = stmt.where(Post.platform == platform)
    if q:
        stmt = stmt.where(or_(Post.hook.ilike(f"%{q}%"), Post.body.ilike(f"%{q}%")))
    return stmt


def list_posts(
    status: PostStatus | None = None, *, platform: Platform | None = None,
    q: str | None = None, sort: str = "newest",
    limit: int | None = None, offset: int = 0,
) -> list[PostSummary]:
    with session_scope() as session:
        stmt = _filtered_posts_stmt(status, platform, q).options(joinedload(Post.topic))
        if sort == "oldest":
            stmt = stmt.order_by(Post.created_at.asc())
        elif sort == "status":
            stmt = stmt.order_by(Post.status, Post.created_at.desc())
        else:
            stmt = stmt.order_by(Post.created_at.desc())
        if limit is not None:
            stmt = stmt.limit(limit).offset(offset)
        posts = list(session.scalars(stmt))

        scheduled_ids = [p.id for p in posts if p.status == PostStatus.SCHEDULED]
        next_runs: dict[int, datetime] = {}
        if scheduled_ids:
            next_runs = {
                pid: run_at
                for pid, run_at in session.execute(
                    select(Schedule.post_id, Schedule.next_run_at)
                    .where(Schedule.post_id.in_(scheduled_ids))
                ).all()
                if pid is not None and run_at is not None
            }
        return [
            _to_summary(p, topic_title=p.topic.title if p.topic else None,
                        scheduled_at=next_runs.get(p.id))
            for p in posts
        ]


def count_posts(status: PostStatus | None = None, *, platform: Platform | None = None,
                q: str | None = None) -> int:
    with session_scope() as session:
        stmt = select(func.count()).select_from(
            _filtered_posts_stmt(status, platform, q).subquery()
        )
        return session.scalar(stmt) or 0


def status_counts() -> dict[str, int]:
    """Đếm số bài theo từng trạng thái (cho bảng tin)."""
    with session_scope() as session:
        rows = session.execute(
            select(Post.status, func.count()).group_by(Post.status)
        ).all()
    return {status.value: n for status, n in rows}


def get_post(post_id: int) -> dict[str, Any]:
    with session_scope() as session:
        p = _require(session, post_id)
        return {
            "id": p.id, "topic_id": p.topic_id, "platform": p.platform.value,
            "language": p.language.value, "status": p.status.value,
            "hook": p.hook, "body": p.body, "draft_body": p.draft_body,
            "previous_body": p.previous_body, "hashtags": p.hashtags, "cta": p.cta,
            "alt_text": p.alt_text, "image_path": p.image_path, "image_prompt": p.image_prompt,
            "citations": p.citations or [], "length": p.length, "tone": p.tone,
            "score": p.score, "review_note": p.review_note, "external_id": p.external_id,
            "topic_title": p.topic.title if p.topic else None,
        }


def approve(post_id: int, actor: str = "human") -> PostStatus:
    with session_scope() as session:
        p = _require(session, post_id)
        if p.status not in _EDITABLE:
            raise ValueError(f"Bài #{post_id} đang ở trạng thái {p.status.value}, không thể duyệt")
        p.status = PostStatus.APPROVED
        p.review_note = None
        _audit(session, "approve", post_id, actor=actor)
        return p.status


def approve_many(post_ids: list[int], actor: str = "human") -> list[int]:
    """Duyệt nhiều bài một lượt; bài không editable được bỏ qua êm."""
    approved: list[int] = []
    with session_scope() as session:
        for pid in post_ids:
            p = session.get(Post, pid)
            if p is None or p.status not in _EDITABLE:
                continue
            p.status = PostStatus.APPROVED
            p.review_note = None
            _audit(session, "approve", pid, actor=actor)
            approved.append(pid)
    return approved


def reject(post_id: int, note: str | None = None, actor: str = "human") -> PostStatus:
    with session_scope() as session:
        p = _require(session, post_id)
        p.status = PostStatus.REJECTED
        if note:
            p.review_note = note
        _audit(session, "reject", post_id, {"note": note}, actor=actor)
        return p.status


def edit(
    post_id: int, *, hook: str | None = None, body: str | None = None,
    hashtags: list[str] | None = None, cta: str | None = None,
    alt_text: str | None = None, image_prompt: str | None = None,
    image_path: str | None = None, actor: str = "human",
) -> None:
    with session_scope() as session:
        p = _require(session, post_id)
        if p.status not in _EDITABLE:
            raise ValueError(f"Bài #{post_id} ({p.status.value}) không cho phép sửa")
        changed: dict[str, Any] = {}
        if hook is not None:
            p.hook = hook
            changed["hook"] = hook
        if body is not None:
            p.body = body
            changed["body"] = "(updated)"
        if hashtags is not None:
            p.hashtags = hashtags
            changed["hashtags"] = hashtags
        if cta is not None:
            p.cta = cta
            changed["cta"] = cta
        if alt_text is not None:
            p.alt_text = alt_text
            changed["alt_text"] = "(updated)"
        if image_prompt is not None:
            p.image_prompt = image_prompt
            changed["image_prompt"] = "(updated)"
        if image_path is not None:
            p.image_path = image_path or None
            changed["image_path"] = image_path
        if changed:
            _audit(session, "edit", post_id, changed, actor=actor)


def revert_body(post_id: int, actor: str = "human") -> bool:
    """Khôi phục body về bản trước lần AI viết lại gần nhất. Trả True nếu có bản để khôi phục."""
    with session_scope() as session:
        p = _require(session, post_id)
        if not p.previous_body:
            return False
        p.body, p.previous_body = p.previous_body, p.body
        _audit(session, "revert_body", post_id, actor=actor)
        return True


def _require(session: Session, post_id: int) -> Post:
    p = session.get(Post, post_id)
    if p is None:
        raise ValueError(f"Không tìm thấy bài #{post_id}")
    return p


# --------------------------------------------------------------------------- #
# Đồng hồ thời-gian-review — lưu qua AuditLog, KHÔNG migration.
# --------------------------------------------------------------------------- #
_TIMER_ACTION = "review_timer"


def _latest_timer_event(session: Session, post_id: int) -> AuditLog | None:
    return session.scalars(
        select(AuditLog)
        .where(AuditLog.action == _TIMER_ACTION, AuditLog.entity_id == post_id)
        .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
        .limit(1)
    ).first()


def timer_running(post_id: int) -> bool:
    with session_scope() as session:
        last = _latest_timer_event(session, post_id)
        return last is not None and (last.detail or {}).get("phase") == "start"


def start_review_timer(post_id: int, actor: str = "human") -> None:
    with session_scope() as session:
        _require(session, post_id)
        last = _latest_timer_event(session, post_id)
        if last is not None and (last.detail or {}).get("phase") == "start":
            return
        _audit(session, _TIMER_ACTION, post_id, {"phase": "start"}, actor=actor)


def stop_review_timer(post_id: int, actor: str = "human") -> float | None:
    with session_scope() as session:
        _require(session, post_id)
        last = _latest_timer_event(session, post_id)
        if last is None or (last.detail or {}).get("phase") != "start":
            return None
        started_at = last.created_at
        if started_at.tzinfo is None:
            started_at = started_at.replace(tzinfo=UTC)
        _audit(session, _TIMER_ACTION, post_id, {"phase": "stop"}, actor=actor)
        return (datetime.now(UTC) - started_at).total_seconds()
