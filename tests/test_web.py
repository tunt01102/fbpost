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

    assert get_post(pid)["status"] == "published"


# --- helpers ---------------------------------------------------------- #
def _mk_draft():
    from fbauto.content.schemas import PostDraft

    return PostDraft(hook="Hook", body="Nội dung bài test đủ dài để qua cổng chất lượng.",
                     hashtags=["cafe"], cta="Ghé ngay")


def _crit():
    from fbauto.content.schemas import Critique

    return Critique(score=90, has_takeaway=True, clarity=90, engagement=90,
                    specificity=85, brand_fit=88)
