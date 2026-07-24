"""Pipeline sinh nội dung FB: outline → draft → critique → refine (bản gọn, không RAG/research)."""

from __future__ import annotations

from collections.abc import Callable

from ..config import get_config
from ..enums import Language, PostLength, PostTone
from . import prompts
from .editor import MAX_REFINES, MIN_GAIN, SCORE_THRESHOLD, score, weak_dimensions
from .llm import LLM
from .schemas import Critique, Outline, PostDraft

# Callback báo tiến trình: on_stage(kind, note) với kind ∈ outline|draft|critique|refine|refine_skip
StageCallback = Callable[[str, str], None]


def generate_draft(
    title: str,
    *,
    llm: LLM | None = None,
    language: Language = Language.VI,
    length: PostLength = PostLength.MEDIUM,
    tone: PostTone = PostTone.PROFESSIONAL,
    brand_hint: str | None = None,
    on_stage: StageCallback | None = None,
) -> tuple[PostDraft, Critique]:
    """Sinh một bài Facebook hoàn chỉnh từ chủ đề. Trả (draft, critique cuối)."""
    llm = llm or LLM()
    system = prompts.system_prompt(language, length=length, tone=tone, brand_hint=brand_hint)

    def _noop(kind: str, note: str = "") -> None:
        return None

    notify: StageCallback = on_stage or _noop
    thinking = get_config().llm.thinking_enabled
    en = language is Language.EN

    # 1) outline
    notify("outline", "")
    outline: Outline = llm.parse(
        system, prompts.outline_user(title, language=language), Outline, thinking=thinking
    )
    if en:
        outline_text = "\n".join([
            f"Angle: {outline.angle}",
            f"Key insight: {outline.key_insight}",
            "Sections:",
            *(f"- {s.point} (support: {s.support})" for s in outline.sections),
            *([f"Example: {outline.concrete_example}"] if outline.concrete_example else []),
            f"Takeaway: {outline.takeaway}",
        ])
    else:
        outline_text = "\n".join([
            f"Góc: {outline.angle}",
            f"Điểm hấp dẫn: {outline.key_insight}",
            "Phân đoạn:",
            *(f"- {s.point} (dẫn chứng: {s.support})" for s in outline.sections),
            *([f"Ví dụ: {outline.concrete_example}"] if outline.concrete_example else []),
            f"Takeaway: {outline.takeaway}",
        ])

    # 2) draft
    notify("draft", "")
    draft: PostDraft = llm.parse(
        system, prompts.draft_user(title, outline_text, language=language),
        PostDraft, thinking=thinking,
    )

    # 3) critique + 4) refine lặp (tối đa MAX_REFINES vòng, dừng sớm nếu tăng < MIN_GAIN)
    notify("critique", "")
    critique = score(draft, llm=llm)
    refines = 0
    while (
        critique.score < SCORE_THRESHOLD
        and refines < MAX_REFINES
        and (critique.issues or critique.suggestions)
    ):
        refines += 1
        notify("refine", f"vòng {refines} — điểm {critique.score} < {SCORE_THRESHOLD}")
        draft = llm.parse(
            system,
            prompts.refine_user(
                draft.body, critique.issues, critique.suggestions,
                weak_dimensions=weak_dimensions(critique), language=language,
            ),
            PostDraft,
        )
        notify("critique", f"chấm lại sau vòng {refines}")
        new_critique = score(draft, llm=llm)
        gain = new_critique.score - critique.score
        critique = new_critique
        if gain < MIN_GAIN:
            break
    if refines == 0:
        notify("refine_skip", f"điểm {critique.score} ≥ {SCORE_THRESHOLD} — không cần")
    return draft, critique
