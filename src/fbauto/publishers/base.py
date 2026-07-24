"""Interface publisher + DryRunPublisher + tiện ích render text."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from ..enums import Platform
from ..models import Post


@dataclass
class PublishResult:
    external_id: str
    dry_run: bool = False
    detail: dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class Publisher(Protocol):
    def publish(self, post: Post) -> PublishResult: ...

    def delete(self, external_id: str) -> None: ...


def render_post_text(post: Post) -> str:
    """Ghép body + CTA + hashtag thành text đăng."""
    parts = [post.body]
    if post.cta:
        parts.append(post.cta)
    if post.hashtags:
        parts.append(" ".join(f"#{t}" for t in post.hashtags))
    return "\n\n".join(parts)


class DryRunPublisher:
    """Không gọi mạng — trả external_id giả. Dùng để test/staging (mặc định an toàn)."""

    def __init__(self, platform: Platform) -> None:
        self.platform = platform

    def publish(self, post: Post) -> PublishResult:
        text = render_post_text(post)
        return PublishResult(
            external_id=f"dryrun-{self.platform.value}-{post.id}",
            dry_run=True,
            detail={"chars": len(text), "has_image": bool(post.image_path)},
        )

    def delete(self, external_id: str) -> None:
        return None
