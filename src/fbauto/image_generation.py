"""Safe Antigravity image generation with validation and atomic replacement."""

from __future__ import annotations

import os
import re
import subprocess
import tempfile
import threading
import xml.etree.ElementTree as ET
from collections.abc import Callable
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

from PIL import Image

from .config import get_config, resolve_path

Runner = Callable[..., subprocess.CompletedProcess[str]]
_RATIOS = {"4:5", "1:1", "16:9"}
_STYLES = {"auto", "product", "lifestyle", "illustration", "minimal"}
_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".svg"}
_PATH_IN_OUTPUT = re.compile(r"(?P<path>/[^\r\n\"'`]+?\.(?:png|jpe?g|webp|svg))", re.I)


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
                "Không chạy Bash, Python hay bất kỳ command nào.",
                "Chỉ dùng công cụ chỉnh sửa/ghi file tích hợp để tạo đúng một file SVG "
                f"tên fbauto-post-{request.post_id}.svg. SVG phải có viewBox phù hợp tỷ lệ, "
                "không dùng script, ảnh, font, link hoặc tài nguyên bên ngoài.",
                "Sau khi ghi file, chỉ trả lời đường dẫn tuyệt đối của file.",
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
                combined_output = "\n".join(filter(None, [proc.stdout, proc.stderr]))
                if "tool required the \"command\" permission" in combined_output:
                    return self._fail(
                        "permission_denied",
                        "Antigravity yêu cầu chạy command nhưng chế độ nền không cho phép.",
                        combined_output,
                    )
                candidates = [
                    p for p in Path(tmp).rglob("*")
                    if p.is_file() and p.suffix.lower() in _IMAGE_EXTS
                ]
                candidates.extend(self._paths_from_output(combined_output, Path(tmp)))
                candidates = list(dict.fromkeys(p.resolve() for p in candidates))
                if len(candidates) != 1:
                    return self._fail(
                        "output_count", "Không tìm thấy đúng một ảnh đầu ra.",
                        f"found={len(candidates)}; output={combined_output[:700]}",
                    )
                src = candidates[0]
                if src.stat().st_size > cfg.image_generation.max_output_bytes:
                    return self._fail("too_large", "Ảnh tạo ra vượt giới hạn 15MB.")
                if src.suffix.lower() == ".svg":
                    svg_error = self._validate_svg(src)
                    if svg_error:
                        return self._fail(
                            "invalid_image",
                            "SVG tạo ra không an toàn hoặc không hợp lệ.",
                            svg_error,
                        )
                else:
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
                suffix = ".png" if src.suffix.lower() == ".svg" else src.suffix.lower()
                dest = dest_dir / f"post-{request.post_id}-ai-{revision}{suffix}"
                staged = dest.with_suffix(dest.suffix + ".tmp")
                if src.suffix.lower() == ".svg":
                    import resvg_py

                    rendered_bytes = resvg_py.svg_to_bytes(
                        svg_string=src.read_text(encoding="utf-8"),
                        width=self._width(request.aspect_ratio),
                        skip_system_fonts=True,
                    )
                    self._write_on_canvas(
                        rendered_bytes, staged,
                        self._width(request.aspect_ratio), self._height(request.aspect_ratio),
                    )
                else:
                    staged.write_bytes(src.read_bytes())
                with Image.open(staged) as rendered:
                    rendered.verify()
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

    @staticmethod
    def _paths_from_output(output: str, workspace: Path) -> list[Path]:
        scratch = Path.home() / ".gemini" / "antigravity-cli" / "scratch"
        allowed = (workspace.resolve(), scratch.resolve())
        result: list[Path] = []
        for match in _PATH_IN_OUTPUT.finditer(output):
            path = Path(match.group("path").strip()).expanduser()
            try:
                resolved = path.resolve(strict=True)
            except OSError:
                continue
            if resolved.suffix.lower() not in _IMAGE_EXTS:
                continue
            if any(resolved == root or root in resolved.parents for root in allowed):
                result.append(resolved)
        return result

    @staticmethod
    def _validate_svg(path: Path) -> str | None:
        try:
            if path.stat().st_size > get_config().image_generation.max_output_bytes:
                return "SVG vượt giới hạn kích thước"
            root = ET.fromstring(path.read_bytes())
            if not root.tag.endswith("svg") or "viewBox" not in root.attrib:
                return "Thiếu thẻ svg hoặc viewBox"
            for element in root.iter():
                tag = element.tag.rsplit("}", 1)[-1].lower()
                if tag in {"script", "image", "foreignobject", "iframe", "audio", "video"}:
                    return f"Không cho phép thẻ {tag}"
                for name, value in element.attrib.items():
                    lowered = value.strip().lower()
                    if name.lower().startswith("on"):
                        return "Không cho phép event handler"
                    external_url = "url(" in lowered and not lowered.startswith("url(#")
                    if "href" in name.lower() or external_url:
                        return "Không cho phép tài nguyên bên ngoài"
            return None
        except (OSError, ET.ParseError) as exc:
            return str(exc)

    @staticmethod
    def _width(ratio: str) -> int:
        return 1080 if ratio in _RATIOS else 1080

    @staticmethod
    def _height(ratio: str) -> int:
        return {"4:5": 1350, "1:1": 1080, "16:9": 608}.get(ratio, 1350)

    @staticmethod
    def _write_on_canvas(data: bytes, destination: Path, width: int, height: int) -> None:
        with Image.open(BytesIO(data)) as rendered:
            image = rendered.convert("RGBA")
        image.thumbnail((width, height), Image.Resampling.LANCZOS)
        canvas = Image.new("RGBA", (width, height), (255, 255, 255, 255))
        canvas.alpha_composite(image, ((width - image.width) // 2, (height - image.height) // 2))
        canvas.convert("RGB").save(destination, format="PNG", optimize=True)


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
