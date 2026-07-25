from types import SimpleNamespace

from fbauto import antigravity_setup as setup


def test_setup_antigravity_success(tmp_path, monkeypatch):
    marker = tmp_path / ".antigravity_setup_complete"
    updates = {}
    monkeypatch.setattr(setup, "SETUP_MARKER", marker)
    monkeypatch.setattr(setup.shutil, "which", lambda binary: "/usr/local/bin/agy")
    monkeypatch.setattr(setup.subprocess, "run", lambda *args, **kwargs: SimpleNamespace(
        returncode=0, stdout="OK\n", stderr="",
    ))
    monkeypatch.setattr(setup, "update_env", lambda values: updates.update(values))
    monkeypatch.setattr(setup, "reload_secrets", lambda: None)

    result = setup.setup_antigravity(force=True)

    assert result["ok"] is True
    assert marker.exists()
    assert updates["LLM_PROVIDER"] == "antigravity_cli"


def test_setup_antigravity_missing_binary(monkeypatch):
    monkeypatch.setattr(setup.shutil, "which", lambda binary: None)
    result = setup.setup_antigravity(force=True)
    assert result["ok"] is False
    assert "agy" in result["error"]


def test_setup_antigravity_existing_marker_skips_call(tmp_path, monkeypatch):
    marker = tmp_path / ".antigravity_setup_complete"
    marker.write_text("ok", encoding="utf-8")
    updates = {}
    monkeypatch.setattr(setup, "SETUP_MARKER", marker)
    monkeypatch.setattr(setup.shutil, "which", lambda binary: "/usr/local/bin/agy")
    monkeypatch.setattr(
        setup.subprocess,
        "run",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("không được gọi agy")),
    )
    monkeypatch.setattr(setup, "update_env", lambda values: updates.update(values))
    monkeypatch.setattr(setup, "reload_secrets", lambda: None)

    result = setup.setup_antigravity()

    assert result["ok"] is True
    assert result["already"] is True
    assert updates["LLM_PROVIDER"] == "antigravity_cli"
