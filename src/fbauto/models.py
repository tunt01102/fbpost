"""Data model (SQLAlchemy 2.0). Bản FB-only: Topic, Post, Schedule, PostLog, AuditLog, Setting."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from .enums import Language, Platform, PostStatus, ScheduleKind, ScheduleMode


def _now() -> datetime:
    return datetime.now(UTC)


def _enum(enum_cls: type) -> SAEnum:
    # native_enum=False -> lưu dạng VARCHAR, portable với SQLite
    return SAEnum(enum_cls, native_enum=False, validate_strings=True)


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Topic(Base, TimestampMixin):
    """Chủ đề người dùng muốn viết (VD: 'khuyến mãi cà phê mùa hè')."""

    __tablename__ = "topics"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(512))
    brand_hint: Mapped[str | None] = mapped_column(Text, nullable=True)  # mô tả thương hiệu/giọng
    language: Mapped[Language] = mapped_column(_enum(Language), default=Language.VI)
    status: Mapped[str] = mapped_column(String(32), default="new")  # new | used

    posts: Mapped[list[Post]] = relationship(back_populates="topic")


class Post(Base, TimestampMixin):
    __tablename__ = "posts"

    id: Mapped[int] = mapped_column(primary_key=True)
    topic_id: Mapped[int] = mapped_column(ForeignKey("topics.id"))
    platform: Mapped[Platform] = mapped_column(_enum(Platform), default=Platform.FACEBOOK_PAGE)
    language: Mapped[Language] = mapped_column(_enum(Language), default=Language.VI)

    hook: Mapped[str | None] = mapped_column(Text, nullable=True)
    body: Mapped[str] = mapped_column(Text)
    # Draft máy GỐC — set lúc tạo, edit() của người KHÔNG đụng (để so sánh / khôi phục).
    draft_body: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Bản body TRƯỚC lần "AI viết lại" gần nhất — cho nút "Quay lại bản trước".
    previous_body: Mapped[str | None] = mapped_column(Text, nullable=True)
    hashtags: Mapped[list[str]] = mapped_column(JSON, default=list)
    cta: Mapped[str | None] = mapped_column(Text, nullable=True)
    alt_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    image_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)  # ảnh có sẵn từ máy
    image_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    citations: Mapped[list[str]] = mapped_column(JSON, default=list)
    length: Mapped[str | None] = mapped_column(String(16), nullable=True)
    tone: Mapped[str | None] = mapped_column(String(16), nullable=True)
    score: Mapped[int | None] = mapped_column(Integer, nullable=True)  # điểm biên tập cuối

    status: Mapped[PostStatus] = mapped_column(_enum(PostStatus), default=PostStatus.DRAFT)
    review_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    external_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    topic: Mapped[Topic] = relationship(back_populates="posts")
    logs: Mapped[list[PostLog]] = relationship(back_populates="post", cascade="all, delete-orphan")


class Schedule(Base, TimestampMixin):
    __tablename__ = "schedules"

    id: Mapped[int] = mapped_column(primary_key=True)
    post_id: Mapped[int | None] = mapped_column(ForeignKey("posts.id"), nullable=True)
    kind: Mapped[ScheduleKind] = mapped_column(_enum(ScheduleKind))
    cron: Mapped[str | None] = mapped_column(String(128), nullable=True)
    time_of_day: Mapped[str | None] = mapped_column(String(8), nullable=True)  # "HH:MM"
    weekday: Mapped[int | None] = mapped_column(Integer, nullable=True)  # 0=Mon .. 6=Sun
    platform: Mapped[Platform] = mapped_column(_enum(Platform), default=Platform.FACEBOOK_PAGE)
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    mode: Mapped[ScheduleMode] = mapped_column(
        _enum(ScheduleMode), default=ScheduleMode.APPROVED_ONLY
    )


class PostLog(Base, TimestampMixin):
    __tablename__ = "post_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    post_id: Mapped[int] = mapped_column(ForeignKey("posts.id"))
    event: Mapped[str] = mapped_column(String(64))
    detail: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    post: Mapped[Post] = relationship(back_populates="logs")


class AuditLog(Base, TimestampMixin):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    actor: Mapped[str] = mapped_column(String(32))  # human | system
    action: Mapped[str] = mapped_column(String(64))
    entity: Mapped[str] = mapped_column(String(64))
    entity_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    detail: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class Setting(Base, TimestampMixin):
    """Cài đặt dạng key-value (chủ đề mặc định, giọng văn thương hiệu…)."""

    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str | None] = mapped_column(Text, nullable=True)
