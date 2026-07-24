"""Fixtures dùng chung: DB tạm + FakeLLM (không gọi mạng/CLI thật)."""

from __future__ import annotations

import pytest

from fbauto.content.schemas import Critique, Outline, OutlineSection, PostDraft


@pytest.fixture(autouse=True)
def temp_db(tmp_path, monkeypatch):
    """Trỏ DB sang file sqlite tạm cho mỗi test; dọn engine trước & sau."""
    # .env tạm rỗng để không đọc secret thật
    env_file = tmp_path / ".env"
    env_file.write_text("LLM_PROVIDER=claude_cli\n", encoding="utf-8")
    monkeypatch.setenv("FBAUTO_ENV_FILE", str(env_file))

    import fbauto.config as config
    from fbauto import db as dbmod

    config.reload_secrets()
    cfg = config.get_config()  # singleton cached — mutate để mọi module thấy cùng DB
    orig = cfg.db_url
    cfg.db_url = f"sqlite:///{tmp_path / 'test.sqlite'}"
    dbmod.reset_engine()
    dbmod.init_db()
    yield
    dbmod.reset_engine()
    cfg.db_url = orig


class FakeLLM:
    """LLM giả: trả sẵn Outline/PostDraft/Critique theo schema, không gọi mạng."""

    def __init__(self, provider: str = "fake", score: int = 92, body: str | None = None) -> None:
        self._provider = provider
        self._score = score
        self._body = body or (
            "Cuối tuần này ghé quán mình nha! ☕\n\n"
            "Mua 1 tặng 1 tất cả món đá xay, áp dụng T7 & CN. "
            "Không gian mát, wifi khoẻ, hợp ngồi làm việc hoặc hẹn hò bạn bè.\n\n"
            "Hẹn gặp cả nhà nhé!"
        )

    @property
    def provider(self) -> str:
        return self._provider

    def cheap_model(self) -> str:
        return "fake-cheap"

    def complete(self, system, user, **kw) -> str:
        return "Xin chào!"

    def parse(self, system, user, schema, **kw):
        if schema is Outline:
            return Outline(
                angle="ưu đãi cuối tuần",
                key_insight="mua 1 tặng 1 hấp dẫn",
                sections=[OutlineSection(point="ưu đãi", support="mua 1 tặng 1")],
                concrete_example="áp dụng T7, CN",
                takeaway="ghé quán cuối tuần",
            )
        if schema is PostDraft:
            return PostDraft(
                hook="Cuối tuần này ghé quán mình nha! ☕",
                body=self._body,
                hashtags=["cafe", "uudai"],
                cta="Nhắn tin đặt bàn ngay!",
                image_prompt="ly cà phê đá xay mát lạnh",
                alt_text="Ly cà phê đá xay",
            )
        if schema is Critique:
            return Critique(
                score=self._score, has_takeaway=True, clarity=90, engagement=90,
                specificity=85, brand_fit=88, issues=[], suggestions=[],
            )
        raise AssertionError(f"FakeLLM chưa hỗ trợ schema {schema}")


@pytest.fixture
def fake_llm():
    return FakeLLM()
