"""Log + alerting (webhook Slack/Discord tuỳ chọn) + đệm cảnh báo cho UI."""

from __future__ import annotations

import logging
from collections import deque
from datetime import UTC, datetime

from ..config import get_secrets

logger = logging.getLogger("fbauto")

_LEVELS = {"info": logging.INFO, "warning": logging.WARNING, "error": logging.ERROR}

# Bộ đệm thông báo gần đây để hiển thị trên UI (không cần bảng DB riêng).
_RECENT: deque[dict] = deque(maxlen=50)


def recent_notifications() -> list[dict]:
    """Các thông báo gần đây (mới nhất trước) cho bảng tin UI."""
    return list(reversed(_RECENT))


def notify(level: str, message: str) -> None:
    """Ghi log + đệm cho UI; nếu có NOTIFY_WEBHOOK_URL thì POST best-effort (không raise)."""
    logger.log(_LEVELS.get(level, logging.INFO), message)
    _RECENT.append({"level": level, "message": message, "ts": datetime.now(UTC)})
    webhook = get_secrets().notify_webhook_url
    if not webhook:
        return
    try:
        import httpx

        text = f"[fbauto] {message}"
        httpx.post(webhook, json={"level": level, "text": text, "content": text}, timeout=10)
    except Exception:  # noqa: BLE001 — alerting không được làm hỏng luồng chính
        logger.exception("Gửi webhook thất bại")
