import time

import pytest
from fastapi.testclient import TestClient

from fbauto import service
from fbauto.web.app import create_app


@pytest.fixture
def client():
    return TestClient(create_app(start_scheduler=False))


def test_pages_load(client):
    for path in ["/", "/create", "/review", "/schedules", "/settings", "/safety", "/help"]:
        r = client.get(path)
        assert r.status_code == 200, path
        assert "FB Auto Poster" in r.text


def test_generate_flow_end_to_end(client, monkeypatch):
    monkeypatch.setattr(service, "generate_draft", lambda *a, **k: (_mk_draft(), _crit()))

    r = client.post(
        "/create",
        data={"title": "khuyến mãi cà phê", "brand_hint": "quán nhỏ",
              "tone": "sharing", "length": "medium", "language": "vi"},
        follow_redirects=False,
    )
    assert r.status_code == 303
    loc = r.headers["location"]
    assert loc.startswith("/generating/")
    job_id = loc.rsplit("/", 1)[-1]

    post_id = None
    for _ in range(50):
        d = client.get(f"/api/job/{job_id}").json()
        if d["status"] == "done":
            post_id = d["post_id"]
            break
        if d["status"] == "error":
            pytest.fail(f"job lỗi: {d.get('error')}")
        time.sleep(0.2)
    assert post_id, "job không hoàn tất kịp"

    # mở bài trong màn duyệt
    r = client.get(f"/review/{post_id}")
    assert r.status_code == 200
    assert "Xem trước" in r.text

    # duyệt bài
    r = client.post(f"/review/{post_id}/approve", follow_redirects=False)
    assert r.status_code == 303
    from fbauto.review.service import get_post

    assert get_post(post_id)["status"] == "approved"


def test_publish_now_dry_run(client, monkeypatch):
    from fbauto.config import get_config

    get_config().dry_run = True
    monkeypatch.setattr(service, "generate_draft", lambda *a, **k: (_mk_draft(), _crit()))
    pid = service.generate_and_store(service.create_topic("x"))["post_id"]
    r = client.post(f"/review/{pid}/publish-now", follow_redirects=False)
    assert r.status_code == 303
    from fbauto.review.service import get_post

    # Dry-run: KHÔNG đăng thật → không được đánh dấu published/external_id.
    post = get_post(pid)
    assert post["status"] == "approved"
    assert not post["external_id"]
    assert post["facebook_url"] is None


def test_publish_now_real_shows_facebook_link(client, monkeypatch):
    """Đăng THẬT (giả lập) → màn duyệt hiển thị URL click được tới bài trên Facebook."""
    from fbauto.config import get_config
    from fbauto.publishers.base import PublishResult
    from fbauto.scheduler import service as sched

    get_config().dry_run = False

    class FakeLivePublisher:
        def publish(self, post):
            ext = f"999_{post.id}"
            return PublishResult(external_id=ext, dry_run=False,
                                 detail={"url": f"https://www.facebook.com/999/posts/{post.id}"})

        def delete(self, external_id):
            return None

    monkeypatch.setattr(sched, "get_publisher", lambda *a, **k: FakeLivePublisher())
    monkeypatch.setattr(service, "generate_draft", lambda *a, **k: (_mk_draft(), _crit()))
    pid = service.generate_and_store(service.create_topic("x"))["post_id"]

    r = client.post(f"/review/{pid}/publish-now", follow_redirects=False)
    assert r.status_code == 303

    from fbauto.review.service import get_post
    post = get_post(pid)
    assert post["status"] == "published"
    assert post["facebook_url"] == f"https://www.facebook.com/999/posts/{pid}"

    # Màn duyệt render link click được (thẻ <a>), không còn là dãy số tĩnh.
    html = client.get(f"/review/{pid}").text
    assert f'href="https://www.facebook.com/999/posts/{pid}"' in html
    assert "Xem bài trên Facebook" in html


def test_image_upload_and_serve(client, monkeypatch):
    """Upload ảnh từ máy → gán vào bài + phục vụ lại được qua /image."""
    monkeypatch.setattr(service, "generate_draft", lambda *a, **k: (_mk_draft(), _crit()))
    pid = service.generate_and_store(service.create_topic("x"))["post_id"]

    png = b"\x89PNG\r\n\x1a\n" + b"fake-image-bytes"
    r = client.post(
        f"/review/{pid}/upload-image",
        files={"image": ("anh.png", png, "image/png")},
        follow_redirects=False,
    )
    assert r.status_code == 303

    from fbauto.review.service import get_post
    path = get_post(pid)["image_path"]
    assert path and path.endswith(f"post{pid}.png")

    img = client.get(f"/review/{pid}/image")
    assert img.status_code == 200
    assert img.content == png

    # Gỡ ảnh
    r = client.post(f"/review/{pid}/remove-image", follow_redirects=False)
    assert r.status_code == 303
    assert get_post(pid)["image_path"] is None


def test_upload_rejects_non_image(client, monkeypatch):
    monkeypatch.setattr(service, "generate_draft", lambda *a, **k: (_mk_draft(), _crit()))
    pid = service.generate_and_store(service.create_topic("x"))["post_id"]
    r = client.post(
        f"/review/{pid}/upload-image",
        files={"image": ("virus.exe", b"MZ...", "application/octet-stream")},
        follow_redirects=False,
    )
    assert r.status_code == 303
    from fbauto.review.service import get_post
    assert get_post(pid)["image_path"] is None


def test_settings_guide_present(client):
    html = client.get("/settings").text
    assert "Hướng dẫn tạo app" in html
    assert "pages_manage_posts" in html
    assert "graph.facebook.com/v20.0/me/accounts" in html
    assert 'class="tip"' in html  # tooltip ⓘ có mặt


# --- helpers ---------------------------------------------------------- #
def _mk_draft():
    from fbauto.content.schemas import PostDraft

    return PostDraft(hook="Hook", body="Nội dung bài test đủ dài để qua cổng chất lượng.",
                     hashtags=["cafe"], cta="Ghé ngay")


def _crit():
    from fbauto.content.schemas import Critique

    return Critique(score=90, has_takeaway=True, clarity=90, engagement=90,
                    specificity=85, brand_fit=88)
