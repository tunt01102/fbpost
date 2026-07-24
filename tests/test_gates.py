from fbauto.enums import Platform
from fbauto.validation.gates import GateInput, run_gates


def _gi(body: str, **kw) -> GateInput:
    return GateInput(platform=Platform.FACEBOOK_PAGE, body=body, **kw)


def test_empty_body_fails():
    r = run_gates(_gi("   "))
    assert not r.passed
    assert any("rỗng" in x.lower() for x in r.reasons)


def test_too_long_fails():
    r = run_gates(_gi("a" * 3000))
    assert not r.passed
    assert any("giới hạn" in x for x in r.reasons)


def test_too_many_hashtags_fails():
    r = run_gates(_gi("Bài viết bình thường đủ dài để không bị chặn vì ngắn.",
                      hashtags=["a", "b", "c", "d", "e", "f"]))
    assert not r.passed


def test_pii_secret_blocked():
    r = run_gates(_gi("Liên hệ mật khẩu: 123456 để nhận ưu đãi nhé các bạn ơi"))
    assert not r.passed
    assert any("nhạy cảm" in x or "secret" in x for x in r.reasons)


def test_dedup_blocks_identical():
    body = "Cuối tuần ghé quán mình nha, mua 1 tặng 1 tất cả các món!"
    r = run_gates(_gi(body, published_bodies=[body]))
    assert not r.passed
    assert any("trùng" in x for x in r.reasons)


def test_fluff_is_warning_not_block():
    r = run_gates(_gi("Chúng tôi là giải pháp toàn diện cho mọi nhu cầu của bạn, uy tín hàng đầu."))
    assert r.passed  # sáo rỗng chỉ cảnh báo, không chặn
    assert any("sáo rỗng" in w for w in r.warnings)


def test_clean_post_passes():
    r = run_gates(_gi("Cuối tuần này quán mình mua 1 tặng 1 món đá xay. Ghé nhé cả nhà! ☕",
                      hashtags=["cafe"], has_takeaway=True))
    assert r.passed
    assert r.reasons == []
