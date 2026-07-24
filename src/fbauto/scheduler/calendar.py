"""Chiếu lịch đăng thành occurrence cụ thể theo tháng cho calendar UI."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select

from ..db import session_scope
from ..enums import PostStatus, ScheduleMode
from ..models import Post
from .service import _detached, build_trigger, list_schedules


@dataclass
class Occurrence:
    dt: datetime
    schedule_id: int
    platform: str
    mode: str
    post_id: int | None
    post_hook: str | None
    source: str  # "assigned" | "queue" | "autogen" | "empty"


def _fire_times_in_month(
    schedule_id: int, tz: str, start: datetime, end: datetime, limit: int = 62
) -> list[datetime]:
    """Các thời điểm kích hoạt của 1 lịch trong [start, end) — dùng chính trigger APScheduler."""
    trigger = build_trigger(_detached(schedule_id), tz)
    times: list[datetime] = []
    prev = None
    now = start
    while len(times) < limit:
        nxt = trigger.get_next_fire_time(prev, now)
        if nxt is None or nxt >= end:
            break
        if nxt >= start:
            times.append(nxt)
        prev, now = nxt, nxt + timedelta(seconds=1)
    return times


def _approved_queue() -> dict[str, list[tuple[int, str | None]]]:
    """Hàng đợi bài APPROVED chưa đăng theo nền tảng (cũ nhất trước)."""
    with session_scope() as session:
        rows = session.execute(
            select(Post.id, Post.platform, Post.hook)
            .where(Post.status == PostStatus.APPROVED, Post.external_id.is_(None))
            .order_by(Post.created_at.asc())
        ).all()
    queues: dict[str, list[tuple[int, str | None]]] = {}
    for pid, platform, hook in rows:
        queues.setdefault(platform.value, []).append((pid, hook))
    return queues


def month_occurrences(
    year: int, month: int, *, tz: str, now: datetime | None = None
) -> dict[date, list[Occurrence]]:
    """Occurrence cụ thể của mọi lịch enabled trong tháng, đã mô phỏng gán bài."""
    zone = ZoneInfo(tz)
    now = now or datetime.now(UTC)
    start_month = datetime(year, month, 1, tzinfo=zone)
    end_month = (
        datetime(year + 1, 1, 1, tzinfo=zone) if month == 12
        else datetime(year, month + 1, 1, tzinfo=zone)
    )
    start = max(start_month, now)
    if start >= end_month:
        return {}

    schedules = [s for s in list_schedules() if s["enabled"]]
    raw: list[tuple[datetime, dict]] = []
    for s in schedules:
        for t in _fire_times_in_month(s["id"], tz, start, end_month):
            raw.append((t, s))
    raw.sort(key=lambda x: x[0])

    queues = _approved_queue()
    assigned_ids = {s["post_id"] for s in schedules if s["post_id"]}
    for platform, q in queues.items():
        queues[platform] = [item for item in q if item[0] not in assigned_ids]

    assigned_hooks: dict[int, str | None] = {}
    if assigned_ids:
        with session_scope() as session:
            assigned_hooks = {
                pid: hook
                for pid, hook in session.execute(
                    select(Post.id, Post.hook).where(Post.id.in_(assigned_ids))
                ).all()
            }

    out: dict[date, list[Occurrence]] = {}
    for t, s in raw:
        platform = s["platform"]
        if s["post_id"]:
            occ = Occurrence(t, s["id"], platform, s["mode"], s["post_id"],
                             assigned_hooks.get(s["post_id"]), "assigned")
        elif s["mode"] in (ScheduleMode.AUTO.value, ScheduleMode.GEN_REVIEW.value):
            occ = Occurrence(t, s["id"], platform, s["mode"], None, None, "autogen")
        else:
            q = queues.get(platform, [])
            pick = q.pop(0) if q else None
            if pick:
                occ = Occurrence(t, s["id"], platform, s["mode"], pick[0], pick[1], "queue")
            else:
                occ = Occurrence(t, s["id"], platform, s["mode"], None, None, "empty")
        out.setdefault(t.astimezone(zone).date(), []).append(occ)
    return out
