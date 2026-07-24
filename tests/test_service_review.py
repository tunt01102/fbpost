import pytest

from fbauto import service
from fbauto.enums import Platform
from fbauto.review import service as review


def test_generate_and_store_creates_needs_review(fake_llm, monkeypatch):
    monkeypatch.setattr(service, "generate_draft",
                        lambda *a, **k: _fake_generate(fake_llm))
    tid = service.create_topic("khuyến mãi cà phê mùa hè", brand_hint="quán nhỏ, thân thiện")
    res = service.generate_and_store(tid, platform=Platform.FACEBOOK_PAGE)
    assert res["post_id"]
    assert res["gate_passed"] is True
    p = review.get_post(res["post_id"])
    assert p["status"] == "needs_review"
    assert p["draft_body"] == p["body"]  # draft gốc = body lúc tạo
    assert p["score"] == 92


def test_review_state_machine(fake_llm, monkeypatch):
    monkeypatch.setattr(service, "generate_draft", lambda *a, **k: _fake_generate(fake_llm))
    tid = service.create_topic("chủ đề")
    pid = service.generate_and_store(tid)["post_id"]

    # sửa
    review.edit(pid, body="Nội dung đã sửa cho dài hơn một chút để hợp lệ.", cta="Ghé ngay!")
    assert review.get_post(pid)["cta"] == "Ghé ngay!"

    # duyệt → APPROVED, không sửa được nữa
    review.approve(pid)
    assert review.get_post(pid)["status"] == "approved"
    with pytest.raises(ValueError):
        review.edit(pid, body="cố sửa sau khi duyệt")


def test_reject_and_counts(fake_llm, monkeypatch):
    monkeypatch.setattr(service, "generate_draft", lambda *a, **k: _fake_generate(fake_llm))
    pid = service.generate_and_store(service.create_topic("x"))["post_id"]
    review.reject(pid, note="chưa hợp")
    assert review.get_post(pid)["status"] == "rejected"
    counts = review.status_counts()
    assert counts.get("rejected", 0) == 1


def test_ai_rewrite_keeps_previous_body(monkeypatch):
    # Fake generate + fake rewrite (không gọi LLM thật)
    from fbauto.content.schemas import PostDraft

    monkeypatch.setattr(service, "generate_draft",
                        lambda *a, **k: _fake_generate(_ScoreLLM(80)))
    pid = service.generate_and_store(service.create_topic("x"))["post_id"]
    orig_body = review.get_post(pid)["body"]

    monkeypatch.setattr(service, "refine_with_feedback",
                        lambda draft, fb, **k: PostDraft(hook="H", body="BẢN VIẾT LẠI MỚI"))
    monkeypatch.setattr(service, "score", lambda draft, **k: _crit(95))
    service.ai_rewrite_post(pid, "ngắn gọn hơn")
    p = review.get_post(pid)
    assert p["body"] == "BẢN VIẾT LẠI MỚI"
    assert p["previous_body"] == orig_body

    # quay lại bản trước
    assert review.revert_body(pid) is True
    assert review.get_post(pid)["body"] == orig_body


def test_review_timer(monkeypatch):
    monkeypatch.setattr(service, "generate_draft", lambda *a, **k: _fake_generate(_ScoreLLM(80)))
    pid = service.generate_and_store(service.create_topic("x"))["post_id"]
    assert review.timer_running(pid) is False
    review.start_review_timer(pid)
    assert review.timer_running(pid) is True
    secs = review.stop_review_timer(pid)
    assert secs is not None and secs >= 0
    assert review.timer_running(pid) is False


# --- helpers ----------------------------------------------------------- #
def _fake_generate(llm):
    from fbauto.content.schemas import PostDraft

    draft = llm.parse(None, None, PostDraft)
    crit = _crit(getattr(llm, "_score", 92))
    return draft, crit


def _crit(score: int):
    from fbauto.content.schemas import Critique

    return Critique(score=score, has_takeaway=True, clarity=90, engagement=90,
                    specificity=85, brand_fit=88)


class _ScoreLLM:
    def __init__(self, score):
        self._score = score

    @property
    def provider(self):
        return "fake"

    def parse(self, system, user, schema, **kw):
        from fbauto.content.schemas import PostDraft

        return PostDraft(hook="Hook test", body="Đây là nội dung bài test đủ dài để qua cổng.",
                         hashtags=["test"], cta="CTA")
