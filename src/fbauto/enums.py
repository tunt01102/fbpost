"""Enums dùng chung. Bản FB-only (v1)."""

from __future__ import annotations

from enum import StrEnum


class Platform(StrEnum):
    FACEBOOK_PAGE = "facebook_page"        # Fanpage qua Graph API (KHUYẾN NGHỊ)
    FACEBOOK_PROFILE = "facebook_profile"  # profile cá nhân qua trình duyệt (rủi ro ToS)


class Language(StrEnum):
    VI = "vi"
    EN = "en"


class PostLength(StrEnum):
    SHORT = "short"
    MEDIUM = "medium"
    LONG = "long"


class PostTone(StrEnum):
    PROFESSIONAL = "professional"  # chuyên nghiệp
    SHARING = "sharing"            # thân thiện / chia sẻ
    FUN = "fun"                    # hài hước


class PostStatus(StrEnum):
    DRAFT = "draft"
    NEEDS_REVIEW = "needs_review"
    APPROVED = "approved"
    SCHEDULED = "scheduled"
    PUBLISHED = "published"
    REJECTED = "rejected"
    FAILED = "failed"


class ScheduleKind(StrEnum):
    ONCE = "once"
    DAILY = "daily"
    WEEKLY = "weekly"
    CRON = "cron"


class ScheduleMode(StrEnum):
    """Mức tự động của một lịch đăng."""

    AUTO = "auto"                    # tự sinh bài + tự đăng nếu qua quality gates
    GEN_REVIEW = "gen_review"        # tự sinh bài chờ duyệt; chỉ đăng bài đã APPROVED
    APPROVED_ONLY = "approved_only"  # chỉ đăng bài đã APPROVED (mặc định, an toàn nhất)


# Nhãn tiếng Việt cho trạng thái bài (dùng trong UI)
STATUS_LABELS_VI: dict[str, str] = {
    "draft": "Nháp",
    "needs_review": "Chờ duyệt",
    "approved": "Đã duyệt",
    "scheduled": "Đã lên lịch",
    "published": "Đã đăng",
    "rejected": "Đã bỏ",
    "failed": "Lỗi",
}

TONE_LABELS_VI: dict[str, str] = {
    "professional": "Chuyên nghiệp",
    "sharing": "Thân thiện / chia sẻ",
    "fun": "Hài hước",
}

PLATFORM_LABELS_VI: dict[str, str] = {
    "facebook_page": "Fanpage (Graph API)",
    "facebook_profile": "Trang cá nhân (trình duyệt)",
}
