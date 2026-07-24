"""Prompt builders cho bài đăng Facebook (tiếng Việt là mặc định)."""

from __future__ import annotations

from ..enums import Language, PostLength, PostTone

# Cụm sáo rỗng nên tránh (fluff gate dùng lại) — bỏ dấu khi so khớp.
BANNED_PHRASES = [
    "trong thời đại số",
    "chìa khoá thành công",
    "chìa khóa thành công",
    "không thể phủ nhận",
    "đừng bỏ lỡ cơ hội",
    "hãy để chúng tôi",
    "giải pháp toàn diện",
    "uy tín hàng đầu",
    "chất lượng vượt trội",
    "sự lựa chọn hoàn hảo",
]

_TONE_VI = {
    PostTone.PROFESSIONAL: "chuyên nghiệp, đáng tin, rõ ràng",
    PostTone.SHARING: "thân thiện, gần gũi như đang trò chuyện với khách quen",
    PostTone.FUN: "vui vẻ, hài hước nhẹ nhàng, có thể dùng emoji hợp lý",
}

_LENGTH_VI = {
    PostLength.SHORT: "ngắn gọn (2-4 câu)",
    PostLength.MEDIUM: "vừa phải (1-2 đoạn ngắn)",
    PostLength.LONG: "chi tiết hơn (2-4 đoạn, vẫn dễ đọc trên điện thoại)",
}


def system_prompt(
    language: Language,
    *,
    length: PostLength = PostLength.MEDIUM,
    tone: PostTone = PostTone.PROFESSIONAL,
    brand_hint: str | None = None,
) -> str:
    lang_line = (
        "Viết hoàn toàn bằng TIẾNG VIỆT tự nhiên."
        if language is Language.VI
        else "Write entirely in natural English."
    )
    parts = [
        "Bạn là chuyên viên nội dung mạng xã hội cho một doanh nghiệp nhỏ (chủ shop/dịch vụ). "
        "Nhiệm vụ: viết bài đăng FACEBOOK khiến người đọc dừng lướt, thấy hữu ích, và muốn "
        "hành động (nhắn tin, đặt hàng, ghé shop).",
        lang_line,
        f"Giọng văn: {_TONE_VI.get(tone, 'chuyên nghiệp')}.",
        f"Độ dài: {_LENGTH_VI.get(length, 'vừa phải')}.",
        "QUY TẮC: mở đầu bằng câu hook mạnh; câu ngắn, xuống dòng thoáng cho dễ đọc trên điện "
        "thoại; KHÔNG sáo rỗng, KHÔNG hứa hẹn quá đà; KHÔNG bịa số liệu; emoji dùng vừa phải. "
        "Nếu có khuyến mãi/ưu đãi thì nêu rõ ràng, trung thực.",
    ]
    if brand_hint:
        parts.append(f"Bối cảnh thương hiệu (bám sát): {brand_hint}")
    return "\n\n".join(parts)


def outline_user(title: str, language: Language = Language.VI) -> str:
    if language is Language.EN:
        return (
            f"Topic: {title}\n\nDraft a short outline for ONE Facebook post: the angle, the key "
            "reason readers care, 2-4 sections, one concrete example, and the takeaway/CTA."
        )
    return (
        f"Chủ đề: {title}\n\nHãy phác dàn ý ngắn cho MỘT bài đăng Facebook: góc tiếp cận, lý do "
        "người đọc quan tâm, 2-4 phân đoạn, một ví dụ cụ thể, và điều muốn người đọc làm (CTA)."
    )


def draft_user(title: str, outline_text: str, language: Language = Language.VI) -> str:
    if language is Language.EN:
        return (
            f"Topic: {title}\n\nOutline:\n{outline_text}\n\nWrite the full Facebook post now "
            "(hook + body + hashtags + CTA + short image idea)."
        )
    return (
        f"Chủ đề: {title}\n\nDàn ý:\n{outline_text}\n\nHãy viết BÀI ĐĂNG FACEBOOK hoàn chỉnh ngay "
        "(hook + thân bài + hashtag + lời kêu gọi hành động + gợi ý ảnh ngắn)."
    )


def refine_user(
    body: str,
    issues: list[str],
    suggestions: list[str],
    *,
    weak_dimensions: list[str] | None = None,
    language: Language = Language.VI,
    user_feedback: str | None = None,
) -> str:
    lines = [f"BÀI HIỆN TẠI:\n{body}\n"]
    if user_feedback:
        lines.append(f"Yêu cầu chỉnh sửa của người dùng (ưu tiên cao nhất): {user_feedback}")
    if weak_dimensions:
        lines.append("Điểm yếu cần cải thiện: " + ", ".join(weak_dimensions))
    if issues:
        lines.append("Vấn đề: " + "; ".join(issues))
    if suggestions:
        lines.append("Gợi ý: " + "; ".join(suggestions))
    lines.append(
        "Hãy viết lại bài cho tốt hơn, GIỮ đúng ý và thông tin gốc, không bịa thêm. "
        "Trả về bài hoàn chỉnh."
    )
    return "\n".join(lines)
