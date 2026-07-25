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
