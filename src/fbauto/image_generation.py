"""Safe Antigravity image generation with validation and atomic replacement."""

from __future__ import annotations

import os
import subprocess
import tempfile
import threading
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from PIL import Image

from .config import get_config, resolve_path

Runner = Callable[..., subprocess.CompletedProcess[str]]
_RATIOS = {"4:5", "1:1", "16:9"}
_STYLES = {"auto", "product", "lifestyle", "illustration", "minimal"}


@dataclass(frozen=True)
class ImageGenerationRequest:
    post_id: int
    prompt: str
    visual_brief: str = ""
    aspect_ratio: str = "4:5"
    style: str = "auto"
    topic: str = ""
    brand_hint: str = ""


@dataclass(frozen=True)
class ImageGenerationResult:
    ok: bool
    image_path: str | None = None
    error_code: str | None = None
    user_message: str = ""
    technical_detail: str = ""


def build_image_prompt(request: ImageGenerationRequest) -> str:
    ratio = request.aspect_ratio if request.aspect_ratio in _RATIOS else "4:5"
    style = request.style if request.style in _STYLES else "auto"
    return "\n".join(
        filter(
            None,
            [
                "Tạo đúng một ảnh minh họa chất lượng cao cho bài Facebook.",
                f"Chủ đề: {request.topic}" if request.topic else "",
                f"Gợi ý thương hiệu: {request.brand_hint}" if request.brand_hint else "",
                f"Mô tả ảnh: {request.prompt}",
                f"Visual brief: {request.visual_brief[:500]}" if request.visual_brief else "",
                f"Tỷ lệ khung hình: {ratio}. Phong cách: {style}.",
                "Bố cục thoáng, chủ thể rõ, safe area phù hợp Facebook mobile.",
                "Không tự tạo logo, watermark, chữ quảng cáo, giá, phần trăm giảm giá, "
                "chứng nhận hay thuộc tính sản phẩm không có trong đầu vào.",
                "Hãy tạo file PNG, JPEG hoặc WebP trong thư mục làm việc hiện tại.",
            ],
        )
    )


class AntigravityImageGenerator:
    def __init__(self, runner: Runner = subprocess.run) -> None:
        self._runner = runner

    def generate(self, request: ImageGenerationRequest) -> ImageGenerationResult:
        cfg = get_config()
        try:
            with tempfile.TemporaryDirectory(prefix=f"fbauto-image-{request.post_id}-") as tmp:
                proc = self._runner(
                    [
                        cfg.llm.antigravity_cli.binary,
                        "--mode",
                        "accept-edits",
                        "-p",
                        build_image_prompt(request),
                    ],
                    cwd=tmp,
                    capture_output=True,
                    text=True,
                    timeout=cfg.image_generation.timeout_seconds,
                    check=False,
                )
                if proc.returncode:
                    return self._fail(
                        "command_failed", "Antigravity chưa tạo được ảnh.", proc.stderr
                    )
                candidates = [
                    p for p in Path(tmp).rglob("*")
                    if p.is_file() and p.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}
                ]
                if len(candidates) != 1:
                    return self._fail(
                        "output_count", "Không tìm thấy đúng một ảnh đầu ra.",
                        f"found={len(candidates)}",
                    )
                src = candidates[0]
                if src.stat().st_size > cfg.image_generation.max_output_bytes:
                    return self._fail("too_large", "Ảnh tạo ra vượt giới hạn 15MB.")
                try:
                    with Image.open(src) as im:
                        im.verify()
                        fmt = (im.format or "").upper()
                    if fmt not in {"PNG", "JPEG", "WEBP"}:
                        raise ValueError(fmt)
                except Exception as exc:  # noqa: BLE001
                    return self._fail(
                        "invalid_image", "File tạo ra không phải ảnh hợp lệ.", str(exc)
                    )
                dest_dir = resolve_path(cfg.image_dir)
                dest_dir.mkdir(parents=True, exist_ok=True)
                revision = max(
                    [
                        int(p.stem.rsplit("-", 1)[-1])
                        for p in dest_dir.glob(f"post-{request.post_id}-ai-*.*")
                        if p.stem.rsplit("-", 1)[-1].isdigit()
                    ] or [0]
                ) + 1
                dest = dest_dir / f"post-{request.post_id}-ai-{revision}{src.suffix.lower()}"
                staged = dest.with_suffix(dest.suffix + ".tmp")
                staged.write_bytes(src.read_bytes())
                os.replace(staged, dest)
                return ImageGenerationResult(True, str(dest), user_message="Đã tạo ảnh minh họa.")
        except subprocess.TimeoutExpired as exc:
            return self._fail("timeout", "Tạo ảnh quá thời gian chờ.", str(exc))
        except OSError as exc:
            return self._fail("unavailable", "Không chạy được Antigravity.", str(exc))

    @staticmethod
    def _fail(code: str, message: str, detail: str = "") -> ImageGenerationResult:
        return ImageGenerationResult(False, error_code=code, user_message=message,
                                     technical_detail=(detail or "")[:1000])


class PostImageLocks:
    def __init__(self) -> None:
        self._guard = threading.Lock()
        self._running: dict[int, str] = {}

    def claim(self, post_id: int, job_id: str) -> str | None:
        with self._guard:
            current = self._running.get(post_id)
            if current:
                return current
            self._running[post_id] = job_id
            return None

    def release(self, post_id: int, job_id: str) -> None:
        with self._guard:
            if self._running.get(post_id) == job_id:
                self._running.pop(post_id, None)

    def running(self, post_id: int) -> str | None:
        with self._guard:
            return self._running.get(post_id)


image_locks = PostImageLocks()
