"""Cổng chất lượng — chạy trước khi bài vào hàng chờ review. Tất định, test được không cần LLM."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

from ..enums import Platform

# Giới hạn cứng theo nền tảng: (max ký tự body, max hashtag). FB ~63k thật nhưng ~2200 là ngưỡng
# "xem thêm"; giữ 2200 để bài gọn, dễ đọc.
PLATFORM_LIMITS: dict[Platform, tuple[int, int]] = {
    Platform.FACEBOOK_PAGE: (2200, 5),
    Platform.FACEBOOK_PROFILE: (2200, 5),
}

# Mẫu nhạy cảm: secret/PII/số điện thoại dạng token
_SECRET_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9]{16,}"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"(?i)\b(password|mật khẩu|api[_ ]?key|secret|token)\b\s*[:=]"),
]


@dataclass
class GateInput:
    platform: Platform
    body: str
    hashtags: list[str] = field(default_factory=list)
    alt_text: str | None = None
    has_image: bool = False
    published_bodies: list[str] = field(default_factory=list)
    has_takeaway: bool | None = None
    citations: list[str] = field(default_factory=list)


@dataclass
class GateResult:
    passed: bool
    reasons: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def length_gate(x: GateInput) -> GateResult:
    max_len, max_tags = PLATFORM_LIMITS.get(x.platform, (2200, 5))
    reasons = []
    if len(x.body) > max_len:
        reasons.append(f"Bài dài {len(x.body)} ký tự > giới hạn {max_len} của Facebook")
    if len(x.hashtags) > max_tags:
        reasons.append(f"{len(x.hashtags)} hashtag > tối đa {max_tags}")
    return GateResult(not reasons, reasons)


def not_empty_gate(x: GateInput) -> GateResult:
    if not x.body or not x.body.strip():
        return GateResult(False, ["Bài rỗng — chưa có nội dung"])
    if len(x.body.strip()) < 20:
        return GateResult(False, ["Bài quá ngắn (dưới 20 ký tự)"])
    return GateResult(True)


def value_first_gate(x: GateInput) -> GateResult:
    if x.has_takeaway is False:
        return GateResult(False, ["Bài thiếu lời kêu gọi/điều mang về rõ ràng"], [])
    has_structure = bool(re.search(r"(^|\n)\s*[-*\d]", x.body))
    if x.has_takeaway is None and len(x.body) < 120 and not has_structure:
        return GateResult(True, [], ["Bài khá ngắn — cân nhắc thêm CTA/ý rõ ràng"])
    return GateResult(True)


def alt_text_gate(x: GateInput) -> GateResult:
    if x.has_image and not (x.alt_text and x.alt_text.strip()):
        return GateResult(True, [], ["Ảnh đính kèm chưa có mô tả (alt-text) — nên bổ sung"])
    return GateResult(True)


def pii_secret_gate(x: GateInput) -> GateResult:
    hits = [p.pattern for p in _SECRET_PATTERNS if p.search(x.body)]
    if hits:
        return GateResult(False, [f"Phát hiện dữ liệu nhạy cảm/secret (mẫu: {len(hits)})"])
    return GateResult(True)


def dedup_gate(x: GateInput) -> GateResult:
    norm = _normalize(x.body)
    for other in x.published_bodies:
        if _normalize(other) == norm:
            return GateResult(False, ["Bài trùng với một bài đã đăng gần đây"])
    return GateResult(True)


def _fold(text: str) -> str:
    """Thường hoá + bỏ dấu tiếng Việt để so khớp cụm sáo rỗng bất chấp biến thể chính tả."""
    norm = unicodedata.normalize("NFD", text.lower())
    return "".join(c for c in norm if unicodedata.category(c) != "Mn").replace("đ", "d")


def fluff_gate(x: GateInput) -> GateResult:
    """Cảnh báo (không chặn) cụm sáo rỗng — deterministic, bỏ dấu/hoa thường."""
    from ..content.prompts import BANNED_PHRASES

    body = _fold(x.body)
    hits = sorted({_fold(p): p for p in BANNED_PHRASES if _fold(p) in body}.values())
    if hits:
        return GateResult(
            True, [], ["Có cụm sáo rỗng nên cân nhắc bỏ: " + ", ".join(f"'{h}'" for h in hits[:5])]
        )
    return GateResult(True)


GATES = [
    not_empty_gate,
    length_gate,
    value_first_gate,
    alt_text_gate,
    pii_secret_gate,
    dedup_gate,
    fluff_gate,
]


def run_gates(x: GateInput) -> GateResult:
    """Chạy tất cả gate; gộp lý do fail + cảnh báo. passed=True nếu không gate nào fail.

    reasons = lý do CHẶN; warnings = cảnh báo mềm không ảnh hưởng passed.
    """
    all_reasons: list[str] = []
    all_warnings: list[str] = []
    for gate in GATES:
        r = gate(x)
        if not r.passed:
            all_reasons.extend(r.reasons)
        all_warnings.extend(r.warnings)
    return GateResult(not all_reasons, all_reasons, all_warnings)


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower())
