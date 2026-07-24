"""Ghi/cập nhật file .env (giữ comment, chmod 600)."""

from __future__ import annotations

import os
from pathlib import Path

from .config import env_path


def update_env(updates: dict[str, str], path: str | Path | None = None) -> Path:
    """Cập nhật các khoá trong .env (chỉ khoá có giá trị mới); tạo file nếu chưa có."""
    target = Path(path) if path else env_path()
    updates = {k: v for k, v in updates.items() if v is not None and v != ""}

    lines: list[str] = []
    if target.exists():
        lines = target.read_text(encoding="utf-8").splitlines()

    seen: set[str] = set()
    out: list[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            key = stripped.split("=", 1)[0].strip()
            if key in updates:
                out.append(f"{key}={updates[key]}")
                seen.add(key)
                continue
        out.append(line)

    for key, value in updates.items():
        if key not in seen:
            out.append(f"{key}={value}")

    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("\n".join(out) + "\n", encoding="utf-8")
    try:
        os.chmod(target, 0o600)
    except OSError:
        pass
    return target
