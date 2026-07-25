"""Thread-safe model catalog backed by ``agy models``."""

from __future__ import annotations

import re
import subprocess
import threading
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from .config import get_config

_SLUG = re.compile(r"^[a-zA-Z0-9._()-]+$")
Runner = Callable[..., subprocess.CompletedProcess[str]]


@dataclass(frozen=True)
class ModelCatalogResult:
    models: list[str]
    cached: bool
    fetched_at: datetime | None
    error: str | None = None


class AntigravityModelCatalog:
    def __init__(self, runner: Runner = subprocess.run, ttl_seconds: int = 300) -> None:
        self._runner = runner
        self._ttl = timedelta(seconds=ttl_seconds)
        self._lock = threading.Lock()
        self._last: ModelCatalogResult | None = None

    def list_models(self, force_refresh: bool = False) -> ModelCatalogResult:
        with self._lock:
            now = datetime.now(UTC)
            if (
                not force_refresh
                and self._last
                and self._last.fetched_at
                and now - self._last.fetched_at < self._ttl
            ):
                return ModelCatalogResult(
                    list(self._last.models), True, self._last.fetched_at, self._last.error
                )
            try:
                proc = self._runner(
                    [get_config().llm.antigravity_cli.binary, "models"],
                    capture_output=True,
                    text=True,
                    timeout=20,
                    check=False,
                )
                if proc.returncode:
                    raise RuntimeError((proc.stderr or proc.stdout or "agy models lỗi").strip())
                models = self._parse(proc.stdout)
                if not models:
                    raise RuntimeError("Không đọc được model hợp lệ từ Antigravity")
                self._last = ModelCatalogResult(models, False, now)
            except (OSError, subprocess.TimeoutExpired, RuntimeError) as exc:
                if self._last and self._last.models:
                    self._last = ModelCatalogResult(
                        self._last.models, True, self._last.fetched_at, str(exc)[:300]
                    )
                else:
                    self._last = ModelCatalogResult([], False, None, str(exc)[:300])
            return self._last

    @staticmethod
    def _parse(output: str) -> list[str]:
        found: list[str] = []
        for line in output.splitlines():
            tokens = re.findall(r"[a-zA-Z0-9._()-]+", line)
            candidates = [t for t in tokens if _SLUG.fullmatch(t) and any(c in t for c in "-._")]
            if candidates:
                slug = candidates[0]
                if slug not in found:
                    found.append(slug)
        return found


model_catalog = AntigravityModelCatalog()
