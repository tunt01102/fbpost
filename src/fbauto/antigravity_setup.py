"""Thiết lập Google Antigravity CLI bằng đăng nhập Google, không dùng API key."""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from typing import Any

from .config import PROJECT_ROOT, get_config, reload_secrets
from .env_writer import update_env

SETUP_MARKER = PROJECT_ROOT / "data" / ".antigravity_setup_complete"


def is_setup_complete() -> bool:
    """Đã từng đăng nhập/test thành công trên máy này."""
    return SETUP_MARKER.exists()


def setup_antigravity(*, force: bool = False) -> dict[str, Any]:
    """Mở Google Sign-In qua `agy -p`, kiểm tra phản hồi và chọn provider cho app.

    Antigravity tự quản lý credential trong system keyring. App chỉ lưu một marker không bí mật.
    """
    cfg = get_config().llm.antigravity_cli
    binary = shutil.which(cfg.binary)
    if binary is None:
        return {
            "ok": False,
            "error": "Chưa tìm thấy lệnh 'agy'. Hãy chạy lại start.command/start.bat để tự cài.",
        }

    if is_setup_complete() and not force:
        update_env({"LLM_PROVIDER": "antigravity_cli"})
        reload_secrets()
        return {"ok": True, "already": True, "output": "Đã thiết lập trước đó."}

    cmd = [
        binary,
        "-p",
        (
            "Không dùng công cụ và không sửa file. "
            "Chỉ trả lời đúng một từ tiếng Việt: OK"
        ),
        "--output-format",
        "text",
    ]
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=cfg.timeout_seconds,
            cwd=tempfile.gettempdir(),
        )
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "Đăng nhập Antigravity quá thời gian chờ."}
    except OSError as exc:
        return {"ok": False, "error": f"Không chạy được agy: {exc}"}

    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip()[:500]
        return {"ok": False, "error": detail or f"agy thoát với mã {proc.returncode}"}

    output = (proc.stdout or "").strip()
    if not output:
        return {"ok": False, "error": "agy không trả về nội dung sau khi đăng nhập."}

    update_env({"LLM_PROVIDER": "antigravity_cli"})
    reload_secrets()
    SETUP_MARKER.parent.mkdir(parents=True, exist_ok=True)
    SETUP_MARKER.write_text(
        "Google Sign-In verified; no credential stored here.\n", encoding="utf-8"
    )
    return {"ok": True, "already": False, "output": output[:200]}
