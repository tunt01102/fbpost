"""Khởi tạo engine & session cho SQLAlchemy. Dùng create_all (không cần Alembic)."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from .config import db_url, get_config, resolve_path

_engine = None
_SessionFactory: sessionmaker[Session] | None = None


def get_engine():
    global _engine
    if _engine is None:
        url = db_url()
        # busy-timeout: job sinh bài chạy thread nền có thể commit song song với web
        connect_args = {"timeout": 30} if url.startswith("sqlite") else {}
        _engine = create_engine(url, echo=False, future=True, connect_args=connect_args)
    return _engine


def get_session_factory() -> sessionmaker[Session]:
    global _SessionFactory
    if _SessionFactory is None:
        _SessionFactory = sessionmaker(bind=get_engine(), expire_on_commit=False, future=True)
    return _SessionFactory


@contextmanager
def session_scope() -> Iterator[Session]:
    """Context manager: commit khi thành công, rollback khi lỗi."""
    session = get_session_factory()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def init_db() -> None:
    """Tạo thư mục dữ liệu + toàn bộ bảng (create_all, idempotent)."""
    from . import models  # noqa: F401 — nạp để đăng ký metadata

    resolve_path("data").mkdir(parents=True, exist_ok=True)
    resolve_path(get_config().image_dir).mkdir(parents=True, exist_ok=True)
    models.Base.metadata.create_all(get_engine())


def reset_engine() -> None:
    """Dọn engine/session (dùng khi test đổi DB giữa chừng)."""
    global _engine, _SessionFactory
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _SessionFactory = None


def backup_db(dest: str | Path | None = None, src: str | Path | None = None) -> Path:
    """Sao lưu file sqlite. Trả về đường dẫn bản sao."""
    import shutil
    from datetime import UTC, datetime

    if src is None:
        url = db_url()
        prefix = "sqlite:///"
        if not url.startswith(prefix):
            raise ValueError("backup_db chỉ hỗ trợ sqlite")
        src = url[len(prefix):]
    src = Path(src)
    if not src.exists():
        raise FileNotFoundError(src)

    if dest is None:
        ts = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
        dest = resolve_path("data/backups") / f"app-{ts}.sqlite"
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dest)
    return dest
