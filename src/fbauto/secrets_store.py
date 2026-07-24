"""Kho secret dùng macOS Keychain (an toàn hơn .env plaintext).

get_secrets() tự lấp đầy các trường còn trống từ keychain (service 'fbauto',
account = tên biến môi trường in hoa). Trên OS khác keychain sẽ bị bỏ qua.
"""

from __future__ import annotations

import subprocess
import sys

SERVICE = "fbauto"


def _available() -> bool:
    return sys.platform == "darwin"


def keychain_get(name: str) -> str | None:
    if not _available():
        return None
    try:
        out = subprocess.run(
            ["security", "find-generic-password", "-s", SERVICE, "-a", name, "-w"],
            capture_output=True, text=True, check=False,
        )
        return out.stdout.strip() or None if out.returncode == 0 else None
    except OSError:
        return None


def keychain_set(name: str, value: str) -> None:
    if not _available():
        raise RuntimeError("Keychain chỉ hỗ trợ macOS")
    subprocess.run(
        ["security", "add-generic-password", "-U", "-s", SERVICE, "-a", name, "-w", value],
        check=True,
    )


def keychain_delete(name: str) -> None:
    if not _available():
        raise RuntimeError("Keychain chỉ hỗ trợ macOS")
    subprocess.run(
        ["security", "delete-generic-password", "-s", SERVICE, "-a", name], check=False
    )


def fill_from_keychain[T](secrets: T) -> T:
    """Với mỗi trường rỗng của Secrets, thử lấy từ keychain theo tên biến in hoa."""
    for field in secrets.__class__.model_fields:  # type: ignore[attr-defined]
        if getattr(secrets, field, "") == "":
            value = keychain_get(field.upper())
            if value:
                setattr(secrets, field, value)
    return secrets
