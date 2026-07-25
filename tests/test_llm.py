import pytest

from fbauto.config import get_config
from fbauto.content.llm import LLM, _extract_json


def test_build_cli_cmd_gemini_substitution():
    cfg = get_config().llm.gemini_cli
    cmd = LLM()._build_cli_cmd(cfg, "xin chào", "gemini-flash-latest")
    assert cmd[0].endswith("gemini") or cmd[0] == "gemini"
    assert "--skip-trust" in cmd
    assert "gemini-flash-latest" in cmd
    assert "xin chào" in cmd


def test_build_cli_cmd_antigravity_ultra():
    cfg = get_config().llm.antigravity_cli
    cmd = LLM()._build_cli_cmd(cfg, "viết bài Facebook", "gemini-3.1-pro-high")
    assert cmd[0].endswith("agy") or cmd[0] == "agy"
    assert "--model" in cmd
    assert "gemini-3.1-pro-high" in cmd
    assert "-p" in cmd
    assert "viết bài Facebook" in cmd


def test_build_cli_cmd_antigravity_auto_omits_model():
    cfg = get_config().llm.antigravity_cli
    cmd = LLM()._build_cli_cmd(cfg, "prompt", "")
    assert "--model" not in cmd


def test_build_cli_cmd_omits_model_when_empty():
    cfg = get_config().llm.gemini_cli
    cmd = LLM()._build_cli_cmd(cfg, "prompt", "")
    assert "-m" not in cmd  # model rỗng → bỏ model_args


def test_build_cli_cmd_codex_exec():
    cfg = get_config().llm.codex_cli
    cmd = LLM()._build_cli_cmd(cfg, "viết bài", "gpt-5")
    assert "exec" in cmd
    assert "viết bài" in cmd


def test_provider_chain_dedup_and_availability(monkeypatch):
    llm = LLM(provider="claude_cli")
    monkeypatch.setattr(get_config().llm, "fallback_providers",
                        ["claude_cli", "gemini_cli", "local"])
    # chỉ 'local' khả dụng (có base_url); các CLI coi như không cài
    monkeypatch.setattr(LLM, "_provider_available",
                        lambda self, p: p == "local")
    chain = llm._providers()
    assert chain[0] == "claude_cli"           # provider chính luôn đứng đầu
    assert "gemini_cli" not in chain          # không khả dụng → loại
    assert chain.count("claude_cli") == 1     # không trùng
    assert "local" in chain


def test_extract_json_ok():
    assert _extract_json('rác {"a": 1} rác') == '{"a": 1}'


def test_extract_json_truncated_raises():
    with pytest.raises(ValueError):
        _extract_json('{"a": 1')
