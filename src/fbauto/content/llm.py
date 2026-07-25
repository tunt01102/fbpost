"""Adapter LLM đa nhà cung cấp: Claude / OpenAI / Gemini / local + CLI subscription.

TRÁI TIM "KHÔNG API": antigravity_cli / claude_cli / gemini_cli / codex_cli gọi CLI chính hãng
(đăng nhập bằng subscription, KHÔNG API key, cost 0) qua subprocess. Interface
complete()/parse()/chat() không đổi nên generator/editor không cần biết provider nào.
Client tạo lười; có thể inject `client` để test (chỉ dùng cho Claude API).
"""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
import tempfile
from collections.abc import Callable
from typing import Any, TypeVar

from pydantic import BaseModel

from ..config import get_config, get_secrets

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)
R = TypeVar("R")

# Provider chạy qua CLI subscription tổng quát (đăng nhập CLI, không API key, cost 0).
# claude_cli giữ đường riêng (dùng --system-prompt); các provider này gộp system vào prompt.
_CLI_PROVIDERS = ("antigravity_cli", "gemini_cli", "codex_cli")


def _record_usage(provider: str, model: str | None, resp: Any) -> None:
    """Ghi token usage (best-effort). Bản FB-only không có module cost → no-op êm."""
    try:
        from ..cost import record_llm  # type: ignore[attr-defined]
    except Exception:  # noqa: BLE001 — không có cost module → bỏ qua
        return
    try:
        in_tok = out_tok = 0
        u = getattr(resp, "usage", None)
        if u is not None:
            in_tok = getattr(u, "input_tokens", None) or getattr(u, "prompt_tokens", 0) or 0
            out_tok = getattr(u, "output_tokens", None) or getattr(u, "completion_tokens", 0) or 0
        else:
            um = getattr(resp, "usage_metadata", None)  # Gemini
            if um is not None:
                in_tok = getattr(um, "prompt_token_count", 0) or 0
                out_tok = getattr(um, "candidates_token_count", 0) or 0
        record_llm(provider, model, int(in_tok), int(out_tok))
    except Exception:  # noqa: BLE001
        pass


class LLM:
    def __init__(self, client: Any = None, provider: str | None = None) -> None:
        self._client = client
        self._provider_override = provider
        self._active_provider: str | None = None

    @property
    def provider(self) -> str:
        if self._active_provider is not None:
            return self._active_provider
        return self._primary()

    def _primary(self) -> str:
        return self._provider_override or (get_secrets().llm_provider or "claude_cli")

    def _provider_available(self, prov: str) -> bool:
        """Provider có đủ điều kiện để thử làm fallback? (tránh fallback sang cái thiếu key/URL)."""
        s = get_secrets()
        if prov == "claude":
            return bool(self._client) or bool(s.anthropic_api_key)
        if prov == "claude_cli":
            return shutil.which(get_config().llm.claude_cli.binary) is not None
        if prov in _CLI_PROVIDERS:
            return shutil.which(self._cli_cfg(prov).binary) is not None
        if prov == "local":
            return bool(s.local_llm_base_url)
        if prov == "openai":
            return bool(s.openai_api_key)
        if prov == "gemini":
            return bool(s.gemini_api_key)
        return False

    def _providers(self) -> list[str]:
        """Provider chính + chuỗi fallback khả dụng (đã loại trùng & cái không cấu hình)."""
        primary = self._primary()
        chain = [primary]
        for fb in get_config().llm.fallback_providers:
            if fb and fb != primary and fb not in chain and self._provider_available(fb):
                chain.append(fb)
        return chain

    def _run(self, fn: Callable[[], R]) -> R:
        """Chạy fn với provider chính; lỗi thì tự thử lần lượt các provider fallback."""
        providers = self._providers()
        first_exc: Exception | None = None
        for i, prov in enumerate(providers):
            prev = self._active_provider
            self._active_provider = prov
            try:
                return fn()
            except Exception as exc:  # noqa: BLE001 — thử provider kế tiếp
                if first_exc is None:
                    first_exc = exc
                if i + 1 < len(providers):
                    logger.warning(
                        "LLM provider '%s' lỗi (%s) → fallback sang '%s'",
                        prov, exc.__class__.__name__, providers[i + 1],
                    )
            finally:
                self._active_provider = prev
        assert first_exc is not None
        raise first_exc

    def _models(self) -> tuple[str, str]:
        """Trả (draft_model, cheap_model) theo provider."""
        prov = self.provider
        cfg = get_config().llm
        if prov in ("claude", "claude_cli"):
            return cfg.draft_model, cfg.cheap_model
        if prov in _CLI_PROVIDERS:
            c = self._cli_cfg(prov)
            return c.draft_model, c.cheap_model
        if prov == "openai":
            return cfg.openai_draft_model, cfg.openai_cheap_model
        if prov == "gemini":
            return cfg.gemini_draft_model, cfg.gemini_cheap_model
        if prov == "local":
            m = get_secrets().local_llm_model or "local-model"
            return m, m
        return cfg.openai_draft_model, cfg.openai_cheap_model

    def _draft(self, model: str | None) -> str:
        return model or self._models()[0]

    def cheap_model(self) -> str:
        return self._models()[1]

    # ------------------------------------------------------------------ #
    # API công khai
    # ------------------------------------------------------------------ #
    def complete(
        self, system: str, user: str, *, model: str | None = None,
        max_tokens: int | None = None, thinking: bool = False,
    ) -> str:
        return self._run(lambda: self._complete_once(system, user, model, max_tokens, thinking))

    def _complete_once(self, system, user, model, max_tokens, thinking) -> str:
        prov = self.provider
        mt = max_tokens or get_config().llm.max_tokens
        if prov == "claude":
            return self._claude_complete(system, user, self._draft(model), mt, thinking)
        if prov == "claude_cli":
            return self._claude_cli_text(system, user, self._draft(model))
        if prov in _CLI_PROVIDERS:
            return self._cli_text(prov, system, user, self._draft(model))
        if prov in ("openai", "local"):
            return self._openai_complete(system, user, self._draft(model), mt)
        if prov == "gemini":
            return self._gemini_complete(system, user, self._draft(model), mt)
        raise ValueError(f"LLM_PROVIDER không hỗ trợ: {prov}")

    def chat(
        self, system: str, messages: list[dict[str, str]], *,
        model: str | None = None, max_tokens: int | None = None,
    ) -> str:
        return self._run(lambda: self._chat_once(system, messages, model, max_tokens))

    def _chat_once(self, system, messages, model, max_tokens) -> str:
        prov = self.provider
        mt = max_tokens or get_config().llm.max_tokens
        if prov == "claude":
            resp = self._anthropic.messages.create(
                model=self._draft(model), max_tokens=mt, system=system, messages=messages,
            )
            _record_usage("claude", self._draft(model), resp)
            return "".join(b.text for b in resp.content if getattr(b, "type", None) == "text")
        if prov == "claude_cli":
            return self._claude_cli_chat(system, messages, self._draft(model))
        if prov in _CLI_PROVIDERS:
            return self._cli_chat(prov, system, messages, self._draft(model))
        if prov in ("openai", "local"):
            resp = self._openai_client().chat.completions.create(
                model=self._draft(model), max_tokens=mt,
                messages=[{"role": "system", "content": system}, *messages],
            )
            _record_usage(prov, self._draft(model), resp)
            return resp.choices[0].message.content or ""
        if prov == "gemini":
            gmodel = self._gemini_model(self._draft(model), system)
            contents = [
                {"role": "model" if m["role"] == "assistant" else "user", "parts": [m["content"]]}
                for m in messages
            ]
            resp = gmodel.generate_content(
                contents, generation_config={"max_output_tokens": max(mt, 4096)}
            )
            _record_usage("gemini", self._draft(model), resp)
            return resp.text or ""
        raise ValueError(f"LLM_PROVIDER không hỗ trợ: {prov}")

    def parse(
        self, system: str, user: str, schema: type[T], *,
        model: str | None = None, max_tokens: int | None = None, thinking: bool = False,
    ) -> T:
        return self._run(
            lambda: self._parse_once(system, user, schema, model, max_tokens, thinking)
        )

    def _parse_once(self, system, user, schema, model, max_tokens, thinking) -> Any:
        prov = self.provider
        mt = max_tokens or get_config().llm.max_tokens
        if prov == "claude":
            return self._claude_parse(system, user, schema, self._draft(model), mt, thinking)
        if prov == "claude_cli":
            return self._claude_cli_parse(system, user, schema, self._draft(model))
        if prov in _CLI_PROVIDERS:
            return self._cli_parse(prov, system, user, schema, self._draft(model))
        if prov in ("openai", "local"):
            return self._openai_parse(system, user, schema, self._draft(model), mt)
        if prov == "gemini":
            return self._gemini_parse(system, user, schema, self._draft(model), mt)
        raise ValueError(f"LLM_PROVIDER không hỗ trợ: {prov}")

    # ------------------------------------------------------------------ #
    # Claude (Anthropic API)
    # ------------------------------------------------------------------ #
    @property
    def _anthropic(self) -> Any:
        if self._client is None:
            import anthropic

            self._client = anthropic.Anthropic(api_key=get_secrets().anthropic_api_key or None)
        return self._client

    def _claude_complete(self, system, user, model, mt, thinking) -> str:
        kwargs: dict[str, Any] = {
            "model": model, "max_tokens": mt, "system": system,
            "messages": [{"role": "user", "content": user}],
        }
        if thinking:
            kwargs["thinking"] = {"type": "adaptive"}
        resp = self._anthropic.messages.create(**kwargs)
        _record_usage("claude", model, resp)
        return "".join(b.text for b in resp.content if getattr(b, "type", None) == "text")

    def _claude_parse(self, system, user, schema, model, mt, thinking=False):
        kwargs: dict[str, Any] = {
            "model": model, "max_tokens": mt, "system": system,
            "messages": [{"role": "user", "content": user}], "output_format": schema,
        }
        if thinking:
            kwargs["thinking"] = {"type": "adaptive"}
            kwargs["max_tokens"] = max(mt, 4096)
        resp = self._anthropic.messages.parse(**kwargs)
        _record_usage("claude", model, resp)
        return resp.parsed_output

    # ------------------------------------------------------------------ #
    # claude_cli — Claude qua SUBSCRIPTION (`claude -p`, không API key, cost 0)
    # ------------------------------------------------------------------ #
    def _claude_cli_text(self, system: str, user: str, model: str) -> str:
        """Gọi `claude -p` headless, trả stdout dạng text.

        Dùng `--system-prompt` để không kéo persona coding-agent/CLAUDE.md vào bài.
        Chạy ở thư mục tạm trung lập nên không nạp CLAUDE.md/skills của repo.
        """
        cfg = get_config().llm.claude_cli
        binary = shutil.which(cfg.binary) or cfg.binary
        cmd = [
            binary, "-p", user,
            "--system-prompt", system,
            "--model", model,
            "--output-format", "text",
            "--no-session-persistence",
            *cfg.extra_args,
        ]
        try:
            proc = subprocess.run(
                cmd, capture_output=True, text=True,
                timeout=cfg.timeout_seconds, cwd=tempfile.gettempdir(),
            )
        except FileNotFoundError as exc:
            raise RuntimeError(f"Không tìm thấy claude CLI ('{cfg.binary}')") from exc
        if proc.returncode != 0:
            raise RuntimeError(
                f"claude -p lỗi (exit {proc.returncode}): {(proc.stderr or '').strip()[:500]}"
            )
        out = (proc.stdout or "").strip()
        if not out:
            raise RuntimeError("claude -p trả về rỗng")
        _record_usage("claude_cli", model, None)
        return out

    def _claude_cli_parse(self, system: str, user: str, schema: type[T], model: str) -> T:
        instruct = (
            f"{system}\n\nCHỈ trả về một object JSON đúng schema, không kèm gì khác:\n"
            f"{json.dumps(schema.model_json_schema())}"
        )
        out = self._claude_cli_text(instruct, user, model)
        return schema.model_validate_json(_extract_json(out))

    def _claude_cli_chat(self, system: str, messages: list[dict[str, str]], model: str) -> str:
        parts = [
            f"{'Assistant' if m['role'] == 'assistant' else 'User'}: {m['content']}"
            for m in messages
        ]
        return self._claude_cli_text(system, "\n\n".join(parts), model)

    # ------------------------------------------------------------------ #
    # CLI subscription tổng quát (Antigravity / Gemini Enterprise / Codex)
    # ------------------------------------------------------------------ #
    def _cli_cfg(self, prov: str) -> Any:
        return getattr(get_config().llm, prov)

    def _build_cli_cmd(self, cfg: Any, prompt: str, model: str) -> list[str]:
        """[binary] + base_args + (model_args nếu có model) + prompt_args + extra_args."""
        binary = shutil.which(cfg.binary) or cfg.binary
        model_part = list(cfg.model_args) if model else []

        def sub(tokens: list[str]) -> list[str]:
            return [t.replace("{prompt}", prompt).replace("{model}", model) for t in tokens]

        return [binary, *sub(cfg.base_args), *sub(model_part), *sub(cfg.prompt_args),
                *cfg.extra_args]

    def _cli_text(self, prov: str, system: str, user: str, model: str) -> str:
        cfg = self._cli_cfg(prov)
        prompt = f"{system}\n\n{user}" if cfg.fold_system and system else user
        cmd = self._build_cli_cmd(cfg, prompt, model)
        try:
            proc = subprocess.run(
                cmd, capture_output=True, text=True,
                timeout=cfg.timeout_seconds, cwd=tempfile.gettempdir(),
            )
        except FileNotFoundError as exc:
            raise RuntimeError(f"Không tìm thấy CLI '{cfg.binary}' cho provider {prov}") from exc
        if proc.returncode != 0:
            raise RuntimeError(
                f"{cfg.binary} lỗi (exit {proc.returncode}): {(proc.stderr or '').strip()[:500]}"
            )
        out = (proc.stdout or "").strip()
        if not out:
            raise RuntimeError(f"{cfg.binary} trả về rỗng")
        _record_usage(prov, model or None, None)
        return out

    def _cli_parse(self, prov: str, system: str, user: str, schema: type[T], model: str) -> T:
        instruct = (
            f"{system}\n\nCHỈ trả về một object JSON đúng schema, không kèm gì khác:\n"
            f"{json.dumps(schema.model_json_schema())}"
        )
        out = self._cli_text(prov, instruct, user, model)
        return schema.model_validate_json(_extract_json(out))

    def _cli_chat(self, prov: str, system: str, messages: list[dict[str, str]], model: str) -> str:
        parts = [
            f"{'Assistant' if m['role'] == 'assistant' else 'User'}: {m['content']}"
            for m in messages
        ]
        return self._cli_text(prov, system, "\n\n".join(parts), model)

    # ------------------------------------------------------------------ #
    # OpenAI / local (OpenAI-compatible)
    # ------------------------------------------------------------------ #
    def _openai_client(self) -> Any:
        from openai import OpenAI

        s = get_secrets()
        if self.provider == "local":
            if not s.local_llm_base_url:
                raise RuntimeError("Thiếu LOCAL_LLM_BASE_URL cho provider local")
            return OpenAI(
                base_url=s.local_llm_base_url, api_key=s.local_llm_api_key or "not-needed",
                timeout=600.0, max_retries=0,
            )
        return OpenAI(api_key=s.openai_api_key)

    def _openai_complete(self, system, user, model, mt) -> str:
        resp = self._openai_client().chat.completions.create(
            model=model, max_tokens=mt,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        )
        _record_usage(self.provider, model, resp)
        return resp.choices[0].message.content or ""

    def _openai_parse(self, system, user, schema, model, mt):
        client = self._openai_client()
        try:
            resp = client.beta.chat.completions.parse(
                model=model, max_tokens=mt,
                messages=[{"role": "system", "content": system},
                          {"role": "user", "content": user}],
                response_format=schema,
            )
            _record_usage(self.provider, model, resp)
            parsed = resp.choices[0].message.parsed
            if parsed is not None:
                return parsed
        except Exception:  # noqa: BLE001 — fallback JSON mode
            pass
        instruct = f"{system}\n\nTrả về JSON đúng schema: {json.dumps(schema.model_json_schema())}"
        resp = client.chat.completions.create(
            model=model, max_tokens=mt, response_format={"type": "json_object"},
            messages=[{"role": "system", "content": instruct}, {"role": "user", "content": user}],
        )
        _record_usage(self.provider, model, resp)
        return schema.model_validate_json(resp.choices[0].message.content or "{}")

    # ------------------------------------------------------------------ #
    # Gemini (API)
    # ------------------------------------------------------------------ #
    def _gemini_model(self, model: str, system: str) -> Any:
        import google.generativeai as genai

        genai.configure(api_key=get_secrets().gemini_api_key)
        return genai.GenerativeModel(model, system_instruction=system)

    def _gemini_complete(self, system, user, model, mt) -> str:
        resp = self._gemini_model(model, system).generate_content(user)
        _record_usage("gemini", model, resp)
        return resp.text or ""

    def _gemini_parse(self, system, user, schema, model, mt):
        gmodel = self._gemini_model(model, system)
        max_out = max(mt, 4096)
        try:
            resp = gmodel.generate_content(
                user,
                generation_config={
                    "response_mime_type": "application/json",
                    "response_schema": _gemini_schema(schema),
                    "max_output_tokens": max_out,
                },
            )
            _record_usage("gemini", model, resp)
            return schema.model_validate_json(resp.text or "{}")
        except Exception:  # noqa: BLE001
            instruct = (
                f"{system}\n\nCHỈ trả về một object JSON đúng schema, không kèm gì khác:\n"
                f"{json.dumps(schema.model_json_schema())}"
            )
            resp = self._gemini_model(model, instruct).generate_content(
                user,
                generation_config={"response_mime_type": "application/json",
                                   "max_output_tokens": max_out},
            )
            _record_usage("gemini", model, resp)
            return schema.model_validate_json(_extract_json(resp.text or "{}"))


def _extract_json(text: str) -> str:
    """Lấy object JSON đầu tiên (cắt ký tự thừa quanh nó)."""
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end <= start:
        raise ValueError(
            "LLM trả JSON không hợp lệ/cắt cụt (có thể do hết token đầu ra hoặc bộ lọc an toàn). "
            "Thử lại, tăng llm.max_tokens, hoặc đổi model."
        )
    return text[start : end + 1]


_GEMINI_SCHEMA_KEYS = {
    "type", "format", "description", "nullable", "enum", "items", "properties", "required",
}


def _gemini_schema(schema: type[BaseModel]) -> dict[str, Any]:
    """Chuyển pydantic schema → dict an toàn cho response_schema của Gemini."""
    root = schema.model_json_schema()
    defs = root.get("$defs", {})

    def conv(node: dict[str, Any]) -> dict[str, Any]:
        if "$ref" in node:
            node = defs.get(node["$ref"].split("/")[-1], {})
        elif "allOf" in node and len(node["allOf"]) == 1:
            merged = {k: v for k, v in node.items() if k != "allOf"}
            merged.update(node["allOf"][0])
            node = merged
        out: dict[str, Any] = {}
        for k, v in node.items():
            if k not in _GEMINI_SCHEMA_KEYS:
                continue
            if k == "properties":
                out[k] = {pk: conv(pv) for pk, pv in v.items()}
            elif k == "items":
                out[k] = conv(v)
            else:
                out[k] = v
        return out

    return conv(root)
