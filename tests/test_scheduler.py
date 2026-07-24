from datetime import UTC, datetime, timedelta

import pytest

from fbauto.db import session_scope
from fbauto.enums import Platform, PostStatus, ScheduleKind, ScheduleMode
from fbauto.models import Post, Topic
from fbauto.publishers.base import DryRunPublisher, PublishResult
from fbauto.scheduler import service as sched


class FakeLivePublisher:
    """Giả lập đăng THẬT (dry_run=False) để test đường ghi DB mà không gọi mạng."""

    def __init__(self, platform=Platform.FACEBOOK_PAGE) -> None:
        self.platform = platform

    def publish(self, post) -> PublishResult:
        ext = f"999_{post.id}"
        return PublishResult(
            external_id=ext, dry_run=False,
            detail={"url": f"https://www.facebook.com/999/posts/{post.id}"},
        )

    def delete(self, external_id: str) -> None:
        return None


def _make_post(status=PostStatus.APPROVED, platform=Platform.FACEBOOK_PAGE, body="Bài test") -> int:
    with session_scope() as s:
        t = Topic(title="chủ đề", status="new")
        s.add(t)
        s.flush()
        p = Post(topic_id=t.id, platform=platform, body=body, status=status)
        s.add(p)
        s.flush()
        return p.id


# --- decide_autopublish (thuần logic) ---------------------------------- #
def test_decide_autopublish_matrix():
    assert sched.decide_autopublish(ScheduleMode.AUTO, True, False) == (True, "auto_ok")
    assert sched.decide_autopublish(ScheduleMode.AUTO, True, True) == (False, "need_human")
    assert sched.decide_autopublish(ScheduleMode.AUTO, False, False) == (False, "gate_failed")
    assert sched.decide_autopublish(ScheduleMode.GEN_REVIEW, True, False) == (False, "gen_review")


# --- idempotency & publish -------------------------------------------- #
def test_real_publish_sets_published_and_external_id():
    pid = _make_post()
    r = sched.publish_post(pid, dry_run=False, publisher=FakeLivePublisher())
    assert not r.dry_run
    p = _get(pid)
    assert p["status"] == "published"
    assert p["external_id"]


def test_dry_run_does_not_mark_published():
    """Dry-run KHÔNG được đặt external_id/PUBLISHED — nếu không sẽ chặn đăng thật sau này."""
    pid = _make_post()
    r = sched.publish_post(pid, dry_run=True)
    assert r.dry_run
    p = _get(pid)
    assert p["status"] == "approved"  # vẫn ở trạng thái cũ
    assert not p["external_id"]
    # Sau khi dry-run, vẫn đăng THẬT được (không bị chống-trùng chặn nhầm).
    r2 = sched.publish_post(pid, dry_run=False, publisher=FakeLivePublisher())
    assert not r2.detail.get("already_published")
    assert _get(pid)["status"] == "published"


def test_publish_is_idempotent():
    pid = _make_post()
    r1 = sched.publish_post(pid, dry_run=False, publisher=FakeLivePublisher())
    r2 = sched.publish_post(pid, dry_run=False, publisher=FakeLivePublisher())  # đã có id → bỏ qua
    assert r2.external_id == r1.external_id
    assert r2.detail.get("already_published")


def test_publish_rejects_non_approved():
    pid = _make_post(status=PostStatus.NEEDS_REVIEW)
    with pytest.raises(ValueError):
        sched.publish_post(pid, dry_run=True)


def test_failed_publish_marks_failed_then_retry():
    pid = _make_post()

    class Boom(DryRunPublisher):
        def publish(self, post):
            raise RuntimeError("mất mạng")

    with pytest.raises(RuntimeError):
        sched.publish_post(pid, dry_run=False, publisher=Boom(Platform.FACEBOOK_PAGE))
    assert _get(pid)["status"] == "failed"
    # retry với publisher tốt → published
    sched.retry_post(pid, dry_run=False, publisher=FakeLivePublisher())
    assert _get(pid)["status"] == "published"


# --- chống spam -------------------------------------------------------- #
def test_frequency_cap():
    from fbauto.config import get_config

    get_config().scheduler.min_hours_between_posts = 6
    pid = _make_post(status=PostStatus.PUBLISHED)
    with session_scope() as s:
        s.get(Post, pid).published_at = datetime.now(UTC)
    assert sched.within_frequency_cap(Platform.FACEBOOK_PAGE) is True
    # bài đăng 10h trước → hết cap
    with session_scope() as s:
        s.get(Post, pid).published_at = datetime.now(UTC) - timedelta(hours=10)
    assert sched.within_frequency_cap(Platform.FACEBOOK_PAGE) is False


def test_daily_cap():
    from fbauto.config import get_config

    get_config().scheduler.max_posts_per_day_per_platform = 1
    pid = _make_post(status=PostStatus.PUBLISHED)
    with session_scope() as s:
        s.get(Post, pid).published_at = datetime.now(UTC)
    assert sched.over_daily_post_cap(Platform.FACEBOOK_PAGE) is True


# --- run_schedule ------------------------------------------------------ #
def test_run_schedule_once_disables_after_run():
    from fbauto.config import get_config

    get_config().scheduler.min_hours_between_posts = 0
    get_config().scheduler.max_posts_per_day_per_platform = 99
    get_config().pause_all_schedules = False
    pid = _make_post()
    sid = sched.add_schedule(
        ScheduleKind.ONCE, Platform.FACEBOOK_PAGE, post_id=pid,
        next_run_at=datetime.now(UTC),
    )
    res = sched.run_schedule(sid, dry_run=True)
    assert res.published_post_id == pid
    rows = {r["id"]: r for r in sched.list_schedules()}
    assert rows[sid]["enabled"] is False  # lịch một-lần tự tắt


def test_run_schedule_respects_pause_all():
    from fbauto.config import get_config

    pid = _make_post()
    sid = sched.add_schedule(
        ScheduleKind.ONCE, Platform.FACEBOOK_PAGE, post_id=pid, next_run_at=datetime.now(UTC),
    )
    get_config().pause_all_schedules = True
    try:
        res = sched.run_schedule(sid, dry_run=True)
        assert res.published_post_id is None
        assert "tạm dừng" in res.skipped_reason
    finally:
        get_config().pause_all_schedules = False


# --- URL bài đã đăng --------------------------------------------------- #
def test_facebook_permalink():
    from fbauto.publishers.facebook_api import facebook_permalink

    assert facebook_permalink("123_456") == "https://www.facebook.com/123/posts/456"
    assert facebook_permalink("789") == "https://www.facebook.com/789"
    assert facebook_permalink("dryrun-facebook_page-1") is None
    assert facebook_permalink(None) is None
    assert facebook_permalink("") is None


# --- build_trigger ----------------------------------------------------- #
def test_parse_hhmm():
    assert sched._parse_hhmm("07:30") == (7, 30)
    assert sched._parse_hhmm(None) == (9, 0)


def _get(pid: int) -> dict:
    from fbauto.review.service import get_post

    return get_post(pid)
