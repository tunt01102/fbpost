"""Tầng ứng dụng: nối sinh bài (generator) + cổng chất lượng (gates) + lưu DB.

Dùng chung bởi web UI, CLI và scheduler (tự sinh). Tách khỏi I/O web để test được.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select

from .config import get_config
from .content.editor import refine_with_feedback, score
from .content.generator import StageCallback, generate_draft
from .content.llm import LLM
from .content.prompts import system_prompt
from .content.schemas import PostDraft
from .db import session_scope
from .enums import Language, Platform, PostLength, PostStatus, PostTone
from .models import Post, PostLog, Topic
from .validation.gates import GateInput, run_gates


# --------------------------------------------------------------------------- #
# Chủ đề
# --------------------------------------------------------------------------- #
def create_topic(title: str, *, brand_hint: str | None = None,
                 language: Language = Language.VI) -> int:
    with session_scope() as session:
        t = Topic(title=title.strip(), brand_hint=brand_hint, language=language, status="new")
        session.add(t)
        session.flush()
        return t.id


def list_topics(status: str | None = None) -> list[dict]:
    with session_scope() as session:
        stmt = select(Topic).order_by(Topic.created_at.desc())
        if status:
            stmt = stmt.where(Topic.status == status)
        return [
            {"id": t.id, "title": t.title, "brand_hint": t.brand_hint,
             "language": t.language.value, "status": t.status}
            for t in session.scalars(stmt)
        ]


# --------------------------------------------------------------------------- #
# Sinh bài + lưu
# --------------------------------------------------------------------------- #
def _recent_published_bodies(platform: Platform, limit: int = 20) -> list[str]:
    with session_scope() as session:
        rows = session.scalars(
            select(Post.body)
            .where(Post.platform == platform, Post.status == PostStatus.PUBLISHED)
            .order_by(Post.created_at.desc())
            .limit(limit)
        ).all()
    return list(rows)


def _apply_gates(draft: PostDraft, platform: Platform, *, has_takeaway: bool | None) -> tuple[
    bool, list[str], list[str]
]:
    gi = GateInput(
        platform=platform,
        body=draft.body,
        hashtags=draft.hashtags,
        alt_text=draft.alt_text,
        has_image=False,
        published_bodies=_recent_published_bodies(platform),
        has_takeaway=has_takeaway,
    )
    r = run_gates(gi)
    return r.passed, r.reasons, r.warnings


def generate_and_store(
    topic_id: int,
    *,
    platform: Platform = Platform.FACEBOOK_PAGE,
    tone: PostTone = PostTone.PROFESSIONAL,
    length: PostLength = PostLength.MEDIUM,
    llm: LLM | None = None,
    on_stage: StageCallback | None = None,
) -> dict[str, Any]:
    """Sinh bài từ một chủ đề, chạy cổng chất lượng, lưu Post trạng thái NEEDS_REVIEW.

    Trả {post_id, gate_passed, score, reasons, warnings}.
    """
    with session_scope() as session:
        topic = session.get(Topic, topic_id)
        if topic is None:
            raise ValueError(f"Không tìm thấy chủ đề #{topic_id}")
        title, brand_hint, language = topic.title, topic.brand_hint, topic.language

    draft, critique = generate_draft(
        title, llm=llm, language=language, length=length, tone=tone,
        brand_hint=brand_hint, on_stage=on_stage,
    )
    passed, reasons, warnings = _apply_gates(
        draft, platform, has_takeaway=critique.has_takeaway
    )
    note_parts: list[str] = []
    if reasons:
        note_parts.append("Cần sửa: " + "; ".join(reasons))
    if warnings:
        note_parts.append("Lưu ý: " + "; ".join(warnings))
    review_note = " | ".join(note_parts) or None

    with session_scope() as session:
        post = Post(
            topic_id=topic_id,
            platform=platform,
            language=language,
            hook=draft.hook,
            body=draft.body,
            draft_body=draft.body,
            hashtags=draft.hashtags,
            cta=draft.cta,
            alt_text=draft.alt_text,
            image_prompt=draft.image_prompt,
            length=length.value,
            tone=tone.value,
            score=critique.score,
            status=PostStatus.NEEDS_REVIEW,
            review_note=review_note,
        )
        session.add(post)
        session.flush()
        pid = post.id
        prov = (llm or LLM()).provider
        session.add(PostLog(
            post_id=pid, event="generated",
            detail={"score": critique.score, "gate_passed": passed, "provider": prov},
        ))
    return {
        "post_id": pid, "gate_passed": passed, "score": critique.score,
        "reasons": reasons, "warnings": warnings,
    }


def create_topic_and_generate(
    title: str, *, brand_hint: str | None = None, language: Language = Language.VI,
    platform: Platform = Platform.FACEBOOK_PAGE, tone: PostTone = PostTone.PROFESSIONAL,
    length: PostLength = PostLength.MEDIUM, llm: LLM | None = None,
    on_stage: StageCallback | None = None,
) -> dict[str, Any]:
    """Tiện ích cho web/CLI: tạo chủ đề rồi sinh bài ngay."""
    topic_id = create_topic(title, brand_hint=brand_hint, language=language)
    return generate_and_store(
        topic_id, platform=platform, tone=tone, length=length, llm=llm, on_stage=on_stage
    )


# --------------------------------------------------------------------------- #
# AI viết lại theo góp ý người dùng (dùng trong màn Review)
# --------------------------------------------------------------------------- #
def ai_rewrite_post(post_id: int, user_feedback: str, *, llm: LLM | None = None) -> dict[str, Any]:
    """Gọi AI viết lại body theo góp ý; giữ bản cũ vào previous_body (cho nút Quay lại)."""
    from .review.service import _require

    with session_scope() as session:
        p = _require(session, post_id)
        cur = PostDraft(
            hook=p.hook or "", body=p.body, hashtags=list(p.hashtags or []),
            cta=p.cta or "", image_prompt=p.image_prompt or "", alt_text=p.alt_text or "",
        )
        language = p.language
    new = refine_with_feedback(cur, user_feedback, llm=llm, language=language)
    crit = score(new, llm=llm)
    with session_scope() as session:
        p = _require(session, post_id)
        p.previous_body = p.body
        p.hook = new.hook or p.hook
        p.body = new.body
        if new.hashtags:
            p.hashtags = new.hashtags
        if new.cta:
            p.cta = new.cta
        p.score = crit.score
        session.add(PostLog(post_id=post_id, event="ai_rewrite",
                            detail={"feedback": user_feedback[:200], "score": crit.score}))
    return {"post_id": post_id, "score": crit.score, "body": new.body}


# --------------------------------------------------------------------------- #
# Cài đặt key-value (chủ đề mặc định, giọng thương hiệu…)
# --------------------------------------------------------------------------- #
def get_setting(key: str, default: str | None = None) -> str | None:
    from .models import Setting

    with session_scope() as session:
        s = session.get(Setting, key)
        return s.value if s is not None else default


def set_setting(key: str, value: str | None) -> None:
    from .models import Setting

    with session_scope() as session:
        s = session.get(Setting, key)
        if s is None:
            session.add(Setting(key=key, value=value))
        else:
            s.value = value


# --------------------------------------------------------------------------- #
# Chẩn đoán first-run (đèn xanh/đỏ)
# --------------------------------------------------------------------------- #
def diagnostics() -> dict[str, Any]:
    """Dò CLI AI + kiểm tra kết nối Facebook → cho màn chẩn đoán (đèn xanh/đỏ)."""
    import shutil

    from .config import get_secrets

    cfg = get_config()
    s = get_secrets()
    from .antigravity_setup import is_setup_complete

    ai = {
        "claude_cli": shutil.which(cfg.llm.claude_cli.binary) is not None,
        "antigravity_cli": shutil.which(cfg.llm.antigravity_cli.binary) is not None,
        "gemini_cli": shutil.which(cfg.llm.gemini_cli.binary) is not None,
        "codex_cli": shutil.which(cfg.llm.codex_cli.binary) is not None,
        "local": bool(s.local_llm_base_url),
    }
    fb_page = bool(s.fb_page_id and s.fb_page_access_token)
    return {
        "provider": s.llm_provider,
        "ai": ai,
        "antigravity_setup_complete": is_setup_complete(),
        "ai_ready": any(ai.values()),
        "fb_page_configured": fb_page,
        "dry_run": cfg.dry_run,
        "pause_all": cfg.pause_all_schedules,
    }


def build_system_preview(language: Language = Language.VI, tone: PostTone = PostTone.PROFESSIONAL,
                         brand_hint: str | None = None) -> str:
    """Trả system prompt (để hiển thị/tham khảo)."""
    return system_prompt(language, tone=tone, brand_hint=brand_hint)
