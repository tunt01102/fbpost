"""Editor-agent: chấm điểm draft theo rubric + hàm viết lại theo góp ý người dùng."""

from __future__ import annotations

from ..enums import Language
from . import prompts
from .llm import LLM
from .schemas import Critique, PostDraft

SCORE_THRESHOLD = 80  # dưới ngưỡng này thì refine (tối đa MAX_REFINES vòng)
MAX_REFINES = 2
MIN_GAIN = 3          # refine tăng dưới mức này thì dừng sớm (tránh lặp vô ích)

_SYSTEM = (
    "Bạn là biên tập viên nội dung mạng xã hội khó tính, chuyên bài đăng Facebook cho doanh "
    "nghiệp nhỏ. Chấm 0-100 cho từng chiều:\n"
    "- clarity: dễ đọc trên điện thoại, câu gọn, bố cục thoáng?\n"
    "- engagement: hook có dừng lướt không, có khiến muốn tương tác/hành động không?\n"
    "- specificity: có chi tiết/ví dụ/con số cụ thể thay vì nói chung chung?\n"
    "- brand_fit: đúng giọng, KHÔNG sáo rỗng, KHÔNG hứa hẹn quá đà, không bịa số liệu?\n\n"
    "score = điểm tổng phản ánh cả 4 chiều + có CTA rõ. Bài chung chung, đúng-nhưng-nhạt "
    "KHÔNG quá 70. issues/suggestions phải cụ thể, chỉ rõ câu/đoạn cần sửa."
)

_DIMENSIONS = {
    "clarity": "độ rõ ràng",
    "engagement": "sức hút",
    "specificity": "độ cụ thể",
    "brand_fit": "đúng giọng thương hiệu",
}


def weak_dimensions(critique: Critique) -> list[str]:
    """Các chiều điểm thấp (<70) để nhắc trong vòng refine. 0 = model không chấm → bỏ qua."""
    return [
        f"{label} ({getattr(critique, dim)}/100)"
        for dim, label in _DIMENSIONS.items()
        if 0 < getattr(critique, dim) < 70
    ]


def _critique_model(llm: LLM) -> str | None:
    if getattr(llm, "provider", "") == "local":
        return llm.cheap_model()
    return None  # None → LLM.parse dùng draft model


def score(draft: PostDraft, llm: LLM | None = None, *, model: str | None = None) -> Critique:
    llm = llm or LLM()
    user = (
        f"HOOK: {draft.hook}\n\nBÀI:\n{draft.body}\n\n"
        f"HASHTAGS: {', '.join(draft.hashtags)}\nCTA: {draft.cta}"
    )
    return llm.parse(_SYSTEM, user, Critique, model=model or _critique_model(llm))


def refine_with_feedback(
    draft: PostDraft,
    user_feedback: str,
    *,
    llm: LLM | None = None,
    system: str | None = None,
    language: Language = Language.VI,
) -> PostDraft:
    """AI viết lại bài theo góp ý bằng lời của người dùng (nút 'AI viết lại theo góp ý')."""
    llm = llm or LLM()
    sys = system or prompts.system_prompt(language)
    user = prompts.refine_user(
        draft.body, [], [], language=language, user_feedback=user_feedback
    )
    return llm.parse(sys, user, PostDraft)
