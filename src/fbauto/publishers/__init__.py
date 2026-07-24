"""Publishers: đăng bài lên Facebook. get_publisher() điều phối theo nền tảng."""

from __future__ import annotations

from ..enums import Platform
from .base import DryRunPublisher, Publisher, PublishResult, render_post_text

__all__ = ["DryRunPublisher", "Publisher", "PublishResult", "render_post_text", "get_publisher"]


def get_publisher(platform: Platform, dry_run: bool = True) -> Publisher:
    """Trả publisher phù hợp. dry_run=True luôn dùng DryRunPublisher (không gọi mạng)."""
    if dry_run:
        return DryRunPublisher(platform)

    if platform == Platform.FACEBOOK_PAGE:
        from .facebook_api import FacebookPagePublisher

        return FacebookPagePublisher()
    if platform == Platform.FACEBOOK_PROFILE:
        from .facebook_browser import FacebookProfilePublisher

        return FacebookProfilePublisher()

    raise ValueError(f"Không hỗ trợ nền tảng: {platform}")
