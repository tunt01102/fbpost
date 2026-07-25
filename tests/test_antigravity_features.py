from __future__ import annotations

import subprocess
from io import BytesIO
from pathlib import Path

from PIL import Image

from fbauto.antigravity_models import AntigravityModelCatalog
from fbauto.image_generation import (
    AntigravityImageGenerator,
    ImageGenerationRequest,
    PostImageLocks,
    build_image_prompt,
)


def test_model_catalog_parses_deduplicates_and_caches():
    calls = []

    def runner(*args, **kwargs):
        calls.append(args)
        return subprocess.CompletedProcess(
            args[0], 0, "gemini-3.1-pro-high description\ngemini-3.1-pro-high\ngpt-oss-120b\n", ""
        )

    catalog = AntigravityModelCatalog(runner=runner)
    first = catalog.list_models()
    second = catalog.list_models()
    assert first.models == ["gemini-3.1-pro-high", "gpt-oss-120b"]
    assert second.cached
    assert len(calls) == 1


def test_image_prompt_has_brief_ratio_style_and_guardrails():
    text = build_image_prompt(ImageGenerationRequest(
        1, "ly cà phê", "xanh lá", "4:5", "product", "ưu đãi", "quán nhỏ"
    ))
    assert "4:5" in text
    assert "product" in text
    assert "xanh lá" in text
    assert "Không tự tạo logo" in text
    assert "phần trăm giảm giá" in text


def test_image_generator_validates_and_moves_atomically(tmp_path, monkeypatch):
    from fbauto.config import get_config

    cfg = get_config()
    old = cfg.image_dir
    cfg.image_dir = str(tmp_path / "images")

    def runner(*args, **kwargs):
        out = BytesIO()
        Image.new("RGB", (20, 25), "red").save(out, "PNG")
        (Path(kwargs["cwd"]) / "result.png").write_bytes(out.getvalue())
        return subprocess.CompletedProcess(args[0], 0, "", "")

    try:
        result = AntigravityImageGenerator(runner).generate(
            ImageGenerationRequest(7, "ảnh sản phẩm")
        )
        assert result.ok
        assert result.image_path and Path(result.image_path).exists()
    finally:
        cfg.image_dir = old


def test_post_image_lock_returns_existing_job():
    locks = PostImageLocks()
    assert locks.claim(1, "a") is None
    assert locks.claim(1, "b") == "a"
    locks.release(1, "a")
    assert locks.claim(1, "b") is None


def test_generator_accepts_safe_svg_path_from_antigravity_stdout(tmp_path, monkeypatch):
    from fbauto.config import get_config

    cfg = get_config()
    old = cfg.image_dir
    cfg.image_dir = str(tmp_path / "images")
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    scratch = Path.home() / ".gemini" / "antigravity-cli" / "scratch"
    scratch.mkdir(parents=True, exist_ok=True)
    svg = scratch / "fbauto-test-safe.svg"
    svg.write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10">'
        '<rect width="10" height="10" fill="#167"/></svg>',
        encoding="utf-8",
    )

    def runner(*args, **kwargs):
        return subprocess.CompletedProcess(args[0], 0, str(svg), "")

    try:
        result = AntigravityImageGenerator(runner).generate(
            ImageGenerationRequest(11, "minh họa")
        )
        assert result.ok
        assert result.image_path and result.image_path.endswith(".png")
        with Image.open(result.image_path) as rendered:
            assert rendered.size == (1080, 1350)
    finally:
        svg.unlink(missing_ok=True)
        cfg.image_dir = old


def test_generator_reports_headless_permission_denial(tmp_path):
    def runner(*args, **kwargs):
        return subprocess.CompletedProcess(
            args[0], 0, 'a tool required the "command" permission', ""
        )

    result = AntigravityImageGenerator(runner).generate(
        ImageGenerationRequest(12, "minh họa")
    )
    assert not result.ok
    assert result.error_code == "permission_denied"
