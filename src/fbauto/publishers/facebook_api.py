"""Đăng lên Facebook Page qua Graph API (v20.0) — đường KHUYẾN NGHỊ, an toàn."""

from __future__ import annotations

import httpx

from ..config import get_secrets
from ..models import Post
from .base import PublishResult, render_post_text

GRAPH = "https://graph.facebook.com/v20.0"


class FacebookPagePublisher:
    """Đăng bài lên Facebook Page. Cần pages_manage_posts + Page access token."""

    def __init__(self, page_id: str | None = None, token: str | None = None) -> None:
        s = get_secrets()
        self.page_id = page_id or s.fb_page_id
        self.token = token or s.fb_page_access_token

    def publish(self, post: Post) -> PublishResult:
        if not (self.page_id and self.token):
            raise RuntimeError(
                "Thiếu kết nối Facebook (Page ID / Page token). "
                "Vào Cài đặt → Kết nối Facebook để nhập."
            )
        text = render_post_text(post)
        image_path = post.image_path
        with httpx.Client(timeout=30) as client:
            if image_path:
                with open(image_path, "rb") as fh:
                    resp = client.post(
                        f"{GRAPH}/{self.page_id}/photos",
                        data={"message": text, "access_token": self.token},
                        files={"source": fh},
                    )
            else:
                resp = client.post(
                    f"{GRAPH}/{self.page_id}/feed",
                    data={"message": text, "access_token": self.token},
                )
            resp.raise_for_status()
            data = resp.json()
        ext = data.get("post_id") or data.get("id")
        if not ext:
            raise RuntimeError(f"Graph API không trả id: {data}")
        return PublishResult(external_id=str(ext), detail={"platform": "facebook_page"})

    def delete(self, external_id: str) -> None:
        with httpx.Client(timeout=30) as client:
            resp = client.delete(f"{GRAPH}/{external_id}", params={"access_token": self.token})
            resp.raise_for_status()

    # -- kiểm tra kết nối (nút "Kiểm tra" trong Cài đặt) ------------------- #
    def check(self) -> dict:
        """Gọi thử Graph API lấy tên Page. Trả {'ok', 'name'|'error'}."""
        if not (self.page_id and self.token):
            return {"ok": False, "error": "Chưa nhập Page ID / Page token"}
        try:
            with httpx.Client(timeout=15) as client:
                resp = client.get(
                    f"{GRAPH}/{self.page_id}",
                    params={"fields": "name", "access_token": self.token},
                )
                resp.raise_for_status()
                return {"ok": True, "name": resp.json().get("name", "(không rõ tên)")}
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": str(exc)[:300]}
