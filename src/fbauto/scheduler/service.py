"""Scheduler: đăng bài APPROVED theo lịch, retry + alert, chống trùng & spam.

Tách logic thuần (publish_post, select, frequency cap, decide_autopublish) khỏi phần
APScheduler để test được mà không cần chạy scheduler thật.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from tenacity import retry, stop_after_attempt, wait_exponential

from ..config import get_config
from ..db import session_scope
from ..enums import Platform, PostStatus, ScheduleKind, ScheduleMode
from ..models import Post, PostLog, Schedule, Topic
from ..observability.notify import notify
from ..publishers import Publisher, PublishResult, get_publisher


def _now() -> datetime:
    return datetime.now(UTC)


# --------------------------------------------------------------------------- #
# Đăng một bài (idempotent, retry)
# --------------------------------------------------------------------------- #
@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=0.05, max=2), reraise=True)
def _do_publish(publisher: Publisher, post: Post) -> PublishResult:
    return publisher.publish(post)


def publish_post(
    post_id: int, *, dry_run: bool = True, publisher: Publisher | None = None
) -> PublishResult:
    """Đăng bài APPROVED. Chống trùng qua external_id. Fail → status FAILED + alert.

    Việc đăng chạy NGOÀI transaction để lỗi không rollback trạng thái FAILED đã ghi.
    """
    with session_scope() as session:
        post = session.get(Post, post_id)
        if post is None:
            raise ValueError(f"Không tìm thấy bài #{post_id}")
        if post.external_id:  # chống trùng: đã đăng rồi thì không đăng lại
            return PublishResult(post.external_id, detail={"already_published": True})
        if post.status not in (PostStatus.APPROVED, PostStatus.SCHEDULED):
            raise ValueError(
                f"Chỉ đăng bài đã duyệt/đã lên lịch (bài #{post_id} đang {post.status.value})"
            )
        _ = (post.body, post.hashtags, post.cta, post.image_path, post.id)
        platform = post.platform
        session.expunge(post)

    pub = publisher or get_publisher(platform, dry_run)

    try:
        result = _do_publish(pub, post)
    except Exception as exc:  # noqa: BLE001
        with session_scope() as s:
            failed = s.get(Post, post_id)
            if failed is not None:
                failed.status = PostStatus.FAILED
                s.add(PostLog(post_id=post_id, event="publish_failed", detail={"error": str(exc)}))
        notify("error", f"Đăng bài #{post_id} thất bại: {exc}")
        raise

    with session_scope() as s:
        done = s.get(Post, post_id)
        if done is None:
            raise ValueError(f"Bài #{post_id} biến mất giữa chừng")
        done.external_id = result.external_id
        done.status = PostStatus.PUBLISHED
        done.published_at = _now()
        s.add(PostLog(
            post_id=post_id, event="published",
            detail={"external_id": result.external_id, "dry_run": result.dry_run},
        ))
    return result


def retry_post(
    post_id: int, *, dry_run: bool = True, publisher: Publisher | None = None
) -> PublishResult:
    """Đăng lại một bài đang FAILED (dead-letter): FAILED → APPROVED → publish."""
    with session_scope() as session:
        post = session.get(Post, post_id)
        if post is None:
            raise ValueError(f"Không tìm thấy bài #{post_id}")
        if post.status != PostStatus.FAILED:
            raise ValueError(f"Chỉ đăng lại bài Lỗi (bài #{post_id} đang {post.status.value})")
        post.status = PostStatus.APPROVED
        session.add(PostLog(post_id=post_id, event="retry"))
    return publish_post(post_id, dry_run=dry_run, publisher=publisher)


# --------------------------------------------------------------------------- #
# Chọn bài & chống spam
# --------------------------------------------------------------------------- #
def within_frequency_cap(platform: Platform, now: datetime | None = None) -> bool:
    """True nếu vừa đăng bài trên nền tảng này trong khoảng min_hours_between_posts."""
    now = now or _now()
    sched = get_config().scheduler
    min_hours = sched.per_platform_min_hours.get(platform.value, sched.min_hours_between_posts)
    with session_scope() as session:
        last = session.scalars(
            select(Post.published_at)
            .where(Post.platform == platform, Post.status == PostStatus.PUBLISHED)
            .order_by(Post.published_at.desc())
            .limit(1)
        ).first()
    if last is None:
        return False
    if last.tzinfo is None:
        last = last.replace(tzinfo=UTC)
    return (now - last) < timedelta(hours=min_hours)


def over_daily_post_cap(platform: Platform, now: datetime | None = None) -> bool:
    """True nếu đã đăng đủ max_posts_per_day_per_platform bài lên nền tảng này hôm nay."""
    from zoneinfo import ZoneInfo

    cap = get_config().scheduler.max_posts_per_day_per_platform
    if cap <= 0:
        return False
    tz = ZoneInfo(get_config().scheduler.timezone)
    now = now or _now()
    start_local = now.astimezone(tz).replace(hour=0, minute=0, second=0, microsecond=0)
    start_utc = start_local.astimezone(UTC)
    with session_scope() as session:
        count = session.scalar(
            select(func.count()).select_from(Post).where(
                Post.platform == platform,
                Post.status == PostStatus.PUBLISHED,
                Post.published_at >= start_utc,
            )
        )
    return (count or 0) >= cap


def select_post_for_schedule(schedule: Schedule) -> int | None:
    """Chọn bài để đăng cho một lịch: bài gắn sẵn, hoặc bài APPROVED cũ nhất."""
    with session_scope() as session:
        if schedule.post_id is not None:
            post = session.get(Post, schedule.post_id)
            if (post and post.status in (PostStatus.APPROVED, PostStatus.SCHEDULED)
                    and not post.external_id):
                return post.id
            return None
        stmt = (
            select(Post.id)
            .where(
                Post.platform == schedule.platform,
                Post.status == PostStatus.APPROVED,
                Post.external_id.is_(None),
            )
            .order_by(Post.created_at.asc())
            .limit(1)
        )
        return session.scalars(stmt).first()


@dataclass
class RunResult:
    published_post_id: int | None
    skipped_reason: str | None = None
    generated_post_id: int | None = None


def decide_autopublish(
    mode: ScheduleMode, gate_passed: bool, require_human_approval: bool
) -> tuple[bool, str]:
    """Chính sách tự đăng bài vừa sinh. Trả (có tự đăng?, mã lý do).

    Mã: 'auto_ok' | 'need_human' | 'gate_failed' | 'gen_review'. Thuần logic, test độc lập.
    """
    if mode != ScheduleMode.AUTO:
        return False, "gen_review"
    if require_human_approval:
        return False, "need_human"
    if not gate_passed:
        return False, "gate_failed"
    return True, "auto_ok"


def _pick_topic_for_schedule() -> int | None:
    """Topic 'new' cũ nhất để tự sinh bài."""
    with session_scope() as session:
        return session.scalars(
            select(Topic.id).where(Topic.status == "new").order_by(Topic.id.asc()).limit(1)
        ).first()


def _generate_for_schedule(schedule: Schedule) -> tuple[int | None, bool, str | None]:
    """Tự sinh bài cho lịch AUTO/GEN_REVIEW. Trả (post_id, gate_passed, skip_reason)."""
    from ..service import generate_and_store

    topic_id = _pick_topic_for_schedule()
    if topic_id is None:
        notify("warning", f"Lịch #{schedule.id}: hết chủ đề mới để tự sinh bài")
        return None, False, "hết chủ đề mới để tự sinh"
    result = generate_and_store(topic_id, platform=schedule.platform)
    with session_scope() as session:
        topic = session.get(Topic, topic_id)
        if topic is not None:
            topic.status = "used"
        session.add(PostLog(
            post_id=result["post_id"], event="auto_generated",
            detail={"schedule_id": schedule.id, "mode": schedule.mode.value,
                    "gate_passed": result["gate_passed"]},
        ))
    return result["post_id"], result["gate_passed"], None


def run_schedule(
    schedule_id: int, *, dry_run: bool = True, now: datetime | None = None,
    publisher: Publisher | None = None,
) -> RunResult:
    """Một lần kích hoạt lịch: (tuỳ mode: tự sinh bài →) chọn bài → kiểm tần suất → đăng."""
    now = now or _now()
    # Công tắc lớn: tạm dừng tất cả lịch tự đăng.
    if get_config().pause_all_schedules:
        return RunResult(None, "đang tạm dừng tất cả lịch đăng")

    with session_scope() as session:
        schedule = session.get(Schedule, schedule_id)
        if schedule is None or not schedule.enabled:
            return RunResult(None, "lịch không tồn tại hoặc đã tắt")
        session.expunge(schedule)

    generated_id: int | None = None
    auto_candidate: int | None = None
    gen_skip: str | None = None

    if schedule.mode in (ScheduleMode.AUTO, ScheduleMode.GEN_REVIEW):
        gate_passed = False
        try:
            generated_id, gate_passed, gen_skip = _generate_for_schedule(schedule)
        except Exception as exc:  # noqa: BLE001
            notify("error", f"Lịch #{schedule_id}: tự sinh bài thất bại ({str(exc)[:200]})")
            gen_skip = f"tự sinh lỗi: {str(exc)[:120]}"

        if generated_id is not None:
            do_publish, reason = decide_autopublish(
                schedule.mode, gate_passed, get_config().review.require_human_approval
            )
            if do_publish:
                from ..review.service import approve

                approve(generated_id, actor="system")
                auto_candidate = generated_id
            elif reason == "need_human":
                notify("warning", f"Lịch #{schedule_id} AUTO nhưng cần người duyệt — bài "
                                  f"#{generated_id} chờ duyệt tay")
            elif reason == "gate_failed":
                notify("warning", f"Bài tự sinh #{generated_id} không qua cổng chất lượng — "
                                  f"chờ duyệt tay")
            else:
                notify("info", f"Đã tự sinh bài #{generated_id} chờ duyệt (lịch #{schedule_id})")

    post_id = auto_candidate or select_post_for_schedule(schedule)
    if post_id is None:
        return RunResult(None, gen_skip or "không có bài đã duyệt phù hợp",
                         generated_post_id=generated_id)
    if over_daily_post_cap(schedule.platform, now):
        cap = get_config().scheduler.max_posts_per_day_per_platform
        notify("warning", f"Đã đạt trần {cap} bài/ngày cho {schedule.platform.value} — hoãn "
                          f"bài #{post_id} (lịch #{schedule_id})")
        return RunResult(None, "đã đạt trần số bài/ngày", generated_post_id=generated_id)
    if within_frequency_cap(schedule.platform, now):
        return RunResult(None, "chưa đủ giãn cách giữa các bài (frequency cap)",
                         generated_post_id=generated_id)

    publish_post(post_id, dry_run=dry_run, publisher=publisher)
    if auto_candidate is not None and not dry_run:
        notify("info", f"AUTO: đã đăng bài #{post_id} (lịch #{schedule_id})")
    if schedule.kind == ScheduleKind.ONCE:
        set_schedule_enabled(schedule_id, False)  # lịch một-lần chạy xong tự tắt
    return RunResult(post_id, generated_post_id=generated_id)


def _detached(schedule_id: int) -> Schedule:
    with session_scope() as session:
        s = session.get(Schedule, schedule_id)
        if s is None:
            raise ValueError(f"Không tìm thấy lịch #{schedule_id}")
        session.expunge(s)
        return s


# --------------------------------------------------------------------------- #
# CRUD lịch
# --------------------------------------------------------------------------- #
def add_schedule(
    kind: ScheduleKind,
    platform: Platform,
    *,
    post_id: int | None = None,
    time_of_day: str | None = None,
    weekday: int | None = None,
    cron: str | None = None,
    next_run_at: datetime | None = None,
    mode: ScheduleMode = ScheduleMode.APPROVED_ONLY,
) -> int:
    if kind == ScheduleKind.ONCE and next_run_at is None:
        raise ValueError("Lịch một-lần bắt buộc có thời điểm (next_run_at)")
    with session_scope() as session:
        s = Schedule(
            kind=kind, platform=platform, post_id=post_id, time_of_day=time_of_day,
            weekday=weekday, cron=cron, next_run_at=next_run_at, enabled=True, mode=mode,
        )
        session.add(s)
        session.flush()
        return s.id


def list_schedules() -> list[dict]:
    with session_scope() as session:
        return [
            {
                "id": s.id, "kind": s.kind.value, "platform": s.platform.value,
                "post_id": s.post_id, "time_of_day": s.time_of_day, "weekday": s.weekday,
                "cron": s.cron, "next_run_at": s.next_run_at, "enabled": s.enabled,
                "mode": s.mode.value,
            }
            for s in session.scalars(select(Schedule).order_by(Schedule.id))
        ]


_UPDATABLE_FIELDS = {
    "kind", "platform", "post_id", "time_of_day", "weekday", "cron",
    "next_run_at", "mode", "enabled",
}


def update_schedule(schedule_id: int, **fields) -> None:
    unknown = set(fields) - _UPDATABLE_FIELDS
    if unknown:
        raise ValueError(f"Field không cho phép sửa: {sorted(unknown)}")
    with session_scope() as session:
        s = session.get(Schedule, schedule_id)
        if s is None:
            raise ValueError(f"Không tìm thấy lịch #{schedule_id}")
        for k, v in fields.items():
            setattr(s, k, v)


def set_schedule_enabled(schedule_id: int, enabled: bool) -> None:
    with session_scope() as session:
        s = session.get(Schedule, schedule_id)
        if s is not None:
            s.enabled = enabled


def toggle_schedule(schedule_id: int) -> None:
    with session_scope() as session:
        s = session.get(Schedule, schedule_id)
        if s is not None:
            s.enabled = not s.enabled


def remove_schedule(schedule_id: int) -> None:
    with session_scope() as session:
        s = session.get(Schedule, schedule_id)
        if s is not None:
            session.delete(s)


# --------------------------------------------------------------------------- #
# APScheduler wiring
# --------------------------------------------------------------------------- #
def build_trigger(schedule: Schedule, timezone: str):
    """Tạo APScheduler trigger từ một Schedule."""
    from apscheduler.triggers.cron import CronTrigger
    from apscheduler.triggers.date import DateTrigger

    if schedule.kind == ScheduleKind.CRON and schedule.cron:
        return CronTrigger.from_crontab(schedule.cron, timezone=timezone)
    if schedule.kind == ScheduleKind.ONCE:
        run_at = schedule.next_run_at
        if run_at is not None and run_at.tzinfo is None:
            run_at = run_at.replace(tzinfo=UTC)
        return DateTrigger(run_date=run_at, timezone=timezone)

    hour, minute = _parse_hhmm(schedule.time_of_day)
    if schedule.kind == ScheduleKind.WEEKLY:
        return CronTrigger(
            day_of_week=schedule.weekday if schedule.weekday is not None else 0,
            hour=hour, minute=minute, timezone=timezone,
        )
    return CronTrigger(hour=hour, minute=minute, timezone=timezone)  # DAILY


def _parse_hhmm(value: str | None) -> tuple[int, int]:
    if not value:
        return 9, 0
    h, _, m = value.partition(":")
    return int(h), int(m or 0)


# Scheduler đang chạy của process này — cho resync_job.
_ACTIVE: dict = {"scheduler": None, "tz": "UTC", "dry_run": True}


def resync_job() -> None:
    sch = _ACTIVE.get("scheduler")
    if sch is not None:
        sync_jobs(sch, _ACTIVE["tz"], _ACTIVE["dry_run"])


def sync_jobs(scheduler, tz: str, dry_run: bool) -> None:
    """Đồng bộ job APScheduler với bảng schedules (thêm/cập nhật/gỡ). Chạy lúc start + định kỳ."""
    rows = {s["id"]: s for s in list_schedules()}
    wanted_ids = {f"schedule-{sid}" for sid, s in rows.items() if s["enabled"]}

    for job in scheduler.get_jobs():
        if job.id.startswith("schedule-") and job.id not in wanted_ids:
            scheduler.remove_job(job.id)

    grace = max(1, get_config().scheduler.misfire_grace_seconds)
    for sid, s in rows.items():
        if not s["enabled"]:
            continue
        sched = _detached(sid)
        scheduler.add_job(
            run_schedule,
            trigger=build_trigger(sched, tz),
            kwargs={"schedule_id": sid, "dry_run": dry_run},
            id=f"schedule-{sid}",
            replace_existing=True,
            coalesce=True,             # máy ngủ dậy không burst-đăng dồn
            misfire_grace_time=grace,  # lỡ quá lâu → APScheduler tự bỏ (không đăng bài lỗi thời)
        )


class SchedulerService:
    """Bọc APScheduler: nạp các Schedule enabled + re-sync định kỳ."""

    def __init__(self, dry_run: bool | None = None) -> None:
        self.dry_run = get_config().dry_run if dry_run is None else dry_run
        self._scheduler = None

    def start(self, block: bool = True) -> None:
        from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
        from apscheduler.schedulers.background import BackgroundScheduler
        from apscheduler.schedulers.blocking import BlockingScheduler
        from apscheduler.triggers.interval import IntervalTrigger

        from ..config import db_url, get_config

        tz = get_config().scheduler.timezone
        cls = BlockingScheduler if block else BackgroundScheduler
        scheduler = cls(jobstores={"default": SQLAlchemyJobStore(url=db_url())}, timezone=tz)
        self._scheduler = scheduler

        _ACTIVE.update(scheduler=scheduler, tz=tz, dry_run=self.dry_run)
        sync_jobs(scheduler, tz, self.dry_run)
        scheduler.add_job(
            resync_job, trigger=IntervalTrigger(minutes=5),
            id="schedules-sync", replace_existing=True,
        )
        n = len(list_schedules())
        notify("info", f"Scheduler khởi động: {n} lịch (dry_run={self.dry_run})")
        scheduler.start()

    def shutdown(self) -> None:
        if self._scheduler is not None:
            self._scheduler.shutdown(wait=False)
