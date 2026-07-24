"""Pydantic schemas cho structured output từ LLM (bản FB-only, gọn)."""

from __future__ import annotations

from pydantic import BaseModel, Field


class OutlineSection(BaseModel):
    point: str = Field(description="Ý chính của phân đoạn")
    support: str = Field(description="Ví dụ / lợi ích / số liệu cụ thể chống lưng cho ý này")


class Outline(BaseModel):
    angle: str = Field(description="Góc tiếp cận chính của bài")
    key_insight: str = Field(description="Điểm hấp dẫn / lý do người đọc quan tâm")
    sections: list[OutlineSection] = Field(
        description="2-4 phân đoạn theo mạch: mở đầu → nội dung chính → chốt"
    )
    concrete_example: str = Field(default="", description="Một ví dụ/tình huống cụ thể sẽ kể")
    takeaway: str = Field(description="Điều người đọc mang về / hành động mong muốn")


class PostDraft(BaseModel):
    hook: str = Field(description="Dòng đầu tiên gây chú ý, dừng lướt")
    body: str = Field(description="Thân bài hoàn chỉnh, đã bao gồm hook ở đầu")
    hashtags: list[str] = Field(default_factory=list, description="3-5 hashtag KHÔNG kèm dấu #")
    cta: str = Field(default="", description="Lời kêu gọi hành động (đặt hàng/nhắn tin/ghé shop…)")
    image_prompt: str = Field(default="", description="Gợi ý ảnh minh hoạ (tiếng Việt, ngắn)")
    alt_text: str = Field(default="", description="Mô tả ảnh cho người khiếm thị")


class Critique(BaseModel):
    score: int = Field(ge=0, le=100, description="Điểm tổng thể 0-100")
    has_takeaway: bool = Field(default=True, description="Có lời kêu gọi/điều mang về rõ ràng?")
    clarity: int = Field(default=0, ge=0, le=100, description="Dễ hiểu, dễ đọc")
    engagement: int = Field(default=0, ge=0, le=100, description="Sức hút, khiến muốn tương tác")
    specificity: int = Field(default=0, ge=0, le=100, description="Cụ thể: ví dụ, con số, chi tiết")
    brand_fit: int = Field(default=0, ge=0, le=100, description="Đúng giọng thương hiệu, không sáo")
    issues: list[str] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)
