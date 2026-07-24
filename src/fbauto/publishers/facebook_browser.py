"""Đăng lên Facebook qua Playwright (tùy chọn) — hỗ trợ cả Fanpage lẫn profile cá nhân.

⚠️ CẢNH BÁO: automation trên trình duyệt (nhất là profile cá nhân) dễ vi phạm ToS và bị
khoá tài khoản. Ưu tiên Facebook Page + Graph API. Chỉ dùng đường này khi hiểu rõ rủi ro.
Cần đăng nhập trước một lần để lưu storage_state (xem save_login_state()).
Yêu cầu: pip install "fbauto[browser]" + `playwright install chromium`.
"""

from __future__ import annotations

import re
from pathlib import Path

from ..config import CONFIG_DIR
from ..models import Post
from .base import PublishResult, render_post_text

_STATE = CONFIG_DIR / "facebook_state.json"


class FacebookProfilePublisher:
    def __init__(self, state_path: str | Path | None = None, page_url: str | None = None) -> None:
        self.state = Path(state_path) if state_path else _STATE
        # Nếu đặt page_url (URL Fanpage) → điều hướng tới trang đó rồi đăng; nếu None → newsfeed.
        self.page_url = page_url

    def publish(self, post: Post) -> PublishResult:
        if not self.state.exists():
            raise RuntimeError(
                f"Chưa có phiên đăng nhập ({self.state}). Vào Cài đặt → Kết nối Facebook → "
                "'Đăng nhập bằng trình duyệt' để đăng nhập một lần."
            )
        text = render_post_text(post)
        from playwright.sync_api import sync_playwright

        target = self.page_url or "https://www.facebook.com/"
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            ctx = browser.new_context(storage_state=str(self.state))
            page = ctx.new_page()
            page.goto(target, wait_until="domcontentloaded")
            page.get_by_role(
                "button", name=re.compile(r"bạn đang nghĩ gì|what's on your mind", re.I)
            ).first.click()
            page.get_by_role("textbox").first.fill(text)
            page.get_by_role("button", name=re.compile(r"^đăng$|^post$", re.I)).first.click()
            page.wait_for_timeout(4000)
            ctx.close()
            browser.close()
        return PublishResult(external_id="fb-browser", detail={"note": "đăng qua trình duyệt"})

    def delete(self, external_id: str) -> None:
        raise NotImplementedError("Gỡ bài qua trình duyệt chưa hỗ trợ")

    @classmethod
    def save_login_state(cls, state_path: str | Path | None = None) -> None:
        """Mở trình duyệt có giao diện để đăng nhập thủ công, lưu cookie/state."""
        path = Path(state_path) if state_path else _STATE
        path.parent.mkdir(parents=True, exist_ok=True)
        from playwright.sync_api import sync_playwright

        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=False)
            ctx = browser.new_context()
            page = ctx.new_page()
            page.goto("https://www.facebook.com/login")
            print("Đăng nhập trong cửa sổ trình duyệt, sau đó nhấn Enter tại đây...")
            input()
            ctx.storage_state(path=str(path))
            browser.close()
        print(f"Đã lưu phiên đăng nhập vào {path}")
