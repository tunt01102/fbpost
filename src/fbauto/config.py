"""Cấu hình: secrets từ .env (pydantic-settings) + config từ config/settings.yaml.

Bản FB-only, cắt cấu hình LinkedIn/X/video/ảnh/RAG/research so với dự án gốc.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = PROJECT_ROOT / "config"


def env_path() -> Path:
    """Đường dẫn file .env (override bằng biến môi trường FBAUTO_ENV_FILE — hữu ích khi test)."""
    return Path(os.environ.get("FBAUTO_ENV_FILE", str(PROJECT_ROOT / ".env")))


# --------------------------------------------------------------------------- #
# Secrets (từ .env / biến môi trường / Keychain)
# --------------------------------------------------------------------------- #
class Secrets(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # LLM provider: claude_cli | gemini_cli | codex_cli | local | claude | openai | gemini
    #  - *_cli: qua SUBSCRIPTION (đăng nhập CLI, KHÔNG API key, cost 0) — mặc định
    #  - claude/openai/gemini: SDK API (cần key, tính phí) — chỉ dùng làm fallback nâng cao
    llm_provider: str = "claude_cli"
    anthropic_api_key: str = ""
    openai_api_key: str = ""
    gemini_api_key: str = ""
    local_llm_base_url: str = ""   # vd http://localhost:11434/v1 (Ollama/LM Studio)
    local_llm_model: str = ""      # vd llama3.1
    local_llm_api_key: str = ""

    # Facebook Fanpage (Graph API) — token là BÍ MẬT, lưu Keychain/.env cục bộ
    fb_page_id: str = ""
    fb_page_access_token: str = ""
    fb_app_id: str = ""
    fb_app_secret: str = ""

    notify_webhook_url: str = ""


# --------------------------------------------------------------------------- #
# App config (từ config/settings.yaml)
# --------------------------------------------------------------------------- #
class ClaudeCliConfig(BaseModel):
    """Provider `claude_cli`: gọi Claude qua SUBSCRIPTION bằng `claude -p` (KHÔNG API key)."""

    binary: str = "claude"
    timeout_seconds: int = 180
    extra_args: list[str] = Field(default_factory=list)


class CliProviderConfig(BaseModel):
    """Provider CLI subscription tổng quát (Gemini CLI / ChatGPT Codex CLI…).

    Lệnh = `[binary] + base_args + (model_args nếu có model) + prompt_args + extra_args`.
    Placeholder: `{prompt}` (đã gộp system+user nếu `fold_system`), `{model}`.
    """

    binary: str
    base_args: list[str] = Field(default_factory=list)
    model_args: list[str] = Field(default_factory=list)
    prompt_args: list[str] = Field(default_factory=lambda: ["-p", "{prompt}"])
    draft_model: str = ""       # "" = để CLI tự dùng model mặc định của tài khoản
    cheap_model: str = ""
    fold_system: bool = True    # CLI không có cờ system → ghép system vào đầu prompt
    timeout_seconds: int = 180
    extra_args: list[str] = Field(default_factory=list)


def _gemini_cli_default() -> CliProviderConfig:
    # `gemini --skip-trust -m <model> -p "<system>\n\n<user>"` (đăng nhập Google, không API key)
    return CliProviderConfig(
        binary="gemini", base_args=["--skip-trust"], model_args=["-m", "{model}"]
    )


def _codex_cli_default() -> CliProviderConfig:
    # `codex exec -m <model> "<system>\n\n<user>"` (Sign in with ChatGPT — Plus/Pro, không API key)
    return CliProviderConfig(
        binary="codex", base_args=["exec"], model_args=["-m", "{model}"],
        prompt_args=["{prompt}"],
    )


class LLMConfig(BaseModel):
    draft_model: str = "claude-opus-4-8"
    cheap_model: str = "claude-haiku-4-5-20251001"
    max_tokens: int = 2048
    thinking_enabled: bool = True
    openai_draft_model: str = "gpt-4o"
    openai_cheap_model: str = "gpt-4o-mini"
    gemini_draft_model: str = "gemini-flash-latest"
    gemini_cheap_model: str = "gemini-flash-lite-latest"
    # Khi provider chính lỗi → tự thử lần lượt các provider này (nếu khả dụng).
    fallback_providers: list[str] = Field(default_factory=lambda: ["local"])
    claude_cli: ClaudeCliConfig = Field(default_factory=ClaudeCliConfig)
    gemini_cli: CliProviderConfig = Field(default_factory=_gemini_cli_default)
    codex_cli: CliProviderConfig = Field(default_factory=_codex_cli_default)


class ReviewConfig(BaseModel):
    # Mặc định BẮT BUỘC người duyệt — điểm bán hàng & an toàn của app.
    require_human_approval: bool = True
    # Ngưỡng điểm biên tập để coi là "qua cổng chất lượng" khi tự sinh.
    autogate_min_score: int = 70


class SchedulerConfig(BaseModel):
    timezone: str = "Asia/Ho_Chi_Minh"
    min_hours_between_posts: int = 6
    max_posts_per_day_per_platform: int = 3  # trần chống spam / rate-limit nền tảng
    per_platform_min_hours: dict[str, int] = Field(default_factory=dict)
    # Bài lỡ giờ quá lâu (giây) → KHÔNG tự đăng âm thầm, hỏi người dùng. 0 = luôn hỏi.
    misfire_grace_seconds: int = 3600


class AppConfig(BaseModel):
    db_url: str = "sqlite:///data/app.sqlite"
    image_dir: str = "data/images"
    # Công tắc lớn: True = tạm dừng TẤT CẢ lịch tự đăng (không bài nào tự đăng).
    pause_all_schedules: bool = False
    # Đăng thật hay chỉ dry-run (in payload, không gọi mạng). Mặc định dry-run cho an toàn.
    dry_run: bool = True
    llm: LLMConfig = Field(default_factory=LLMConfig)
    review: ReviewConfig = Field(default_factory=ReviewConfig)
    scheduler: SchedulerConfig = Field(default_factory=SchedulerConfig)


def load_yaml(name: str) -> dict[str, Any]:
    path = CONFIG_DIR / name
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    if not isinstance(data, dict):
        raise ValueError(f"{name}: nội dung YAML phải là mapping ở cấp cao nhất")
    return data


@lru_cache(maxsize=1)
def get_secrets() -> Secrets:
    s = Secrets(_env_file=str(env_path()))  # type: ignore[call-arg]
    from .secrets_store import fill_from_keychain

    return fill_from_keychain(s)


def reload_secrets() -> Secrets:
    """Xoá cache & đọc lại secret (gọi sau khi ghi .env)."""
    get_secrets.cache_clear()
    return get_secrets()


@lru_cache(maxsize=1)
def get_config() -> AppConfig:
    return AppConfig.model_validate(load_yaml("settings.yaml"))


def reload_config() -> AppConfig:
    get_config.cache_clear()
    return get_config()


def save_config(cfg: AppConfig) -> None:
    """Ghi config ra settings.yaml (giữ nguyên toàn bộ cây) + refresh cache."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    data = cfg.model_dump(mode="json")
    with (CONFIG_DIR / "settings.yaml").open("w", encoding="utf-8") as fh:
        yaml.safe_dump(data, fh, allow_unicode=True, sort_keys=False)
    get_config.cache_clear()


def resolve_path(relative: str) -> Path:
    p = Path(relative)
    return p if p.is_absolute() else PROJECT_ROOT / p


def db_url() -> str:
    """db_url với đường dẫn sqlite tuyệt đối để chạy được từ bất kỳ CWD nào."""
    url = get_config().db_url
    prefix = "sqlite:///"
    if url.startswith(prefix):
        rel = url[len(prefix):]
        return prefix + str(resolve_path(rel))
    return url
