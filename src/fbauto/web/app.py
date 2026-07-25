"""FastAPI app: giao diện web tiếng Việt cho FB Auto Poster (mặc định http://localhost:8791)."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .. import service
from ..config import get_config, get_secrets, reload_secrets, save_config
from ..db import init_db
from ..enums import (
    PLATFORM_LABELS_VI,
    STATUS_LABELS_VI,
    TONE_LABELS_VI,
    Language,
    Platform,
    PostLength,
    PostStatus,
    PostTone,
    ScheduleKind,
    ScheduleMode,
)
from ..observability.notify import notify, recent_notifications
from ..review import service as review
from ..scheduler import service as sched
from . import jobs

_HERE = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(_HERE / "templates"))

# Ảnh cho phép đính kèm (upload từ máy người dùng).
_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"}
_MAX_IMAGE_BYTES = 15 * 1024 * 1024  # 15MB


def _tz() -> ZoneInfo:
    return ZoneInfo(get_config().scheduler.timezone)


def _fmt_dt(value: datetime | None) -> str:
    if value is None:
        return ""
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(_tz()).strftime("%H:%M %d/%m/%Y")


templates.env.filters["dt"] = _fmt_dt
templates.env.globals.update(
    STATUS_LABELS_VI=STATUS_LABELS_VI,
    TONE_LABELS_VI=TONE_LABELS_VI,
    PLATFORM_LABELS_VI=PLATFORM_LABELS_VI,
)


def create_app(start_scheduler: bool = True) -> FastAPI:
    from contextlib import asynccontextmanager

    _scheduler_holder: dict = {}

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        init_db()
        if start_scheduler:
            try:
                svc = sched.SchedulerService()
                svc.start(block=False)
                _scheduler_holder["svc"] = svc
            except Exception as exc:  # noqa: BLE001 — web vẫn chạy dù scheduler lỗi
                notify("error", f"Không khởi động được bộ hẹn giờ: {exc}")
        yield
        svc = _scheduler_holder.get("svc")
        if svc is not None:
            svc.shutdown()

    app = FastAPI(title="FB Auto Poster", lifespan=lifespan)
    app.mount("/static", StaticFiles(directory=str(_HERE / "static")), name="static")

    # ------------------------------------------------------------------ #
    # Bảng tin
    # ------------------------------------------------------------------ #
    @app.get("/", response_class=HTMLResponse)
    def dashboard(request: Request):
        counts = review.status_counts()
        return templates.TemplateResponse(request, "dashboard.html", {
            "request": request,
            "counts": counts,
            "diag": service.diagnostics(),
            "notifications": recent_notifications()[:8],
            "cfg": get_config(),
        })

    # ------------------------------------------------------------------ #
    # Tạo bài
    # ------------------------------------------------------------------ #
    @app.get("/create", response_class=HTMLResponse)
    def create_form(request: Request):
        return templates.TemplateResponse(request, "create.html", {
            "request": request,
            "default_topic": service.get_setting("default_topic", ""),
            "default_brand": service.get_setting("brand_hint", ""),
        })

    @app.post("/create")
    def create_submit(
        title: str = Form(...),
        brand_hint: str = Form(""),
        tone: str = Form("professional"),
        length: str = Form("medium"),
        language: str = Form("vi"),
    ):
        job_id = jobs.start_generate_job(
            title.strip(),
            brand_hint=brand_hint.strip() or None,
            language=Language(language),
            tone=PostTone(tone),
            length=PostLength(length),
        )
        return RedirectResponse(f"/generating/{job_id}", status_code=303)

    @app.get("/generating/{job_id}", response_class=HTMLResponse)
    def generating(request: Request, job_id: str):
        return templates.TemplateResponse(request, "generating.html", {
            "request": request, "job_id": job_id,
        })

    @app.get("/api/job/{job_id}")
    def job_status(job_id: str):
        job = jobs.get_job(job_id)
        if job is None:
            return JSONResponse({"status": "error", "error": "Không tìm thấy job"}, 404)
        data = {"status": job.status, "stage": job.stage, "log": job.log[-6:]}
        if job.status == "done" and job.result:
            data["post_id"] = job.result["post_id"]
        if job.status == "error":
            data["error"] = job.error
        return JSONResponse(data)

    # ------------------------------------------------------------------ #
    # Duyệt & Sửa
    # ------------------------------------------------------------------ #
    @app.get("/review", response_class=HTMLResponse)
    def review_list(request: Request, status: str = "needs_review", q: str = ""):
        st = PostStatus(status) if status in {s.value for s in PostStatus} else None
        posts = review.list_posts(status=st, q=q or None, limit=200)
        return templates.TemplateResponse(request, "review_list.html", {
            "request": request, "posts": posts, "status": status, "q": q,
            "counts": review.status_counts(),
        })

    @app.get("/review/{post_id}", response_class=HTMLResponse)
    def review_detail(request: Request, post_id: int):
        post = review.get_post(post_id)
        return templates.TemplateResponse(request, "review_detail.html", {
            "request": request, "post": post,
            "editable": review.is_editable_status(post["status"]),
            "tz": get_config().scheduler.timezone,
            "dry_run": get_config().dry_run,
        })

    @app.post("/review/{post_id}/edit")
    def review_edit(
        post_id: int,
        hook: str = Form(""),
        body: str = Form(...),
        hashtags: str = Form(""),
        cta: str = Form(""),
        alt_text: str = Form(""),
        image_path: str = Form(""),
    ):
        tags = [t.strip().lstrip("#") for t in hashtags.replace(",", " ").split() if t.strip()]
        review.edit(post_id, hook=hook, body=body, hashtags=tags, cta=cta,
                    alt_text=alt_text, image_path=image_path)
        return RedirectResponse(f"/review/{post_id}", status_code=303)

    @app.post("/review/{post_id}/upload-image")
    async def review_upload_image(post_id: int, image: UploadFile = File(...)):
        """Nhận ảnh upload từ máy người dùng → lưu vào thư mục ảnh → gán vào bài.

        Tránh việc người dùng phải tự gõ đường dẫn file (họ thường không biết cách lấy).
        """
        from ..config import get_config, resolve_path

        # Kiểm tra bài có cho sửa không TRƯỚC khi ghi file (tránh để lại file mồ côi).
        post = review.get_post(post_id)
        if not review.is_editable_status(post["status"]):
            notify("error", f"Bài #{post_id} đã ở trạng thái "
                            f"{STATUS_LABELS_VI.get(post['status'], post['status'])} — "
                            f"không đính kèm ảnh được nữa.")
            return RedirectResponse(f"/review/{post_id}", status_code=303)
        if not image or not image.filename:
            notify("warning", "Chưa chọn ảnh.")
            return RedirectResponse(f"/review/{post_id}", status_code=303)
        suffix = Path(image.filename).suffix.lower()
        if suffix not in _IMAGE_EXTS:
            notify("error", f"File không phải ảnh hợp lệ ({suffix or 'không rõ'}). "
                            f"Chỉ nhận: {', '.join(sorted(_IMAGE_EXTS))}")
            return RedirectResponse(f"/review/{post_id}", status_code=303)
        data = await image.read()
        if len(data) > _MAX_IMAGE_BYTES:
            notify("error", "Ảnh quá lớn (tối đa 15MB).")
            return RedirectResponse(f"/review/{post_id}", status_code=303)
        img_dir = resolve_path(get_config().image_dir)
        img_dir.mkdir(parents=True, exist_ok=True)
        dest = img_dir / f"post{post_id}{suffix}"
        dest.write_bytes(data)
        try:
            review.edit(post_id, image_path=str(dest))
            notify("info", f"Đã đính kèm ảnh cho bài #{post_id}.")
        except ValueError as exc:
            notify("error", str(exc))
        return RedirectResponse(f"/review/{post_id}", status_code=303)

    @app.post("/review/{post_id}/remove-image")
    def review_remove_image(post_id: int):
        try:
            review.edit(post_id, image_path="")
            notify("info", f"Đã gỡ ảnh khỏi bài #{post_id}.")
        except ValueError as exc:
            notify("error", str(exc))
        return RedirectResponse(f"/review/{post_id}", status_code=303)

    @app.get("/review/{post_id}/image")
    def review_image(post_id: int):
        """Phục vụ ảnh đã đính kèm của bài (chỉ đúng file đường dẫn lưu trong bài)."""
        post = review.get_post(post_id)
        path = post.get("image_path")
        if not path or not Path(path).exists():
            return JSONResponse({"error": "no image"}, status_code=404)
        return FileResponse(path)

    @app.post("/review/{post_id}/ai-rewrite")
    def review_ai_rewrite(post_id: int, feedback: str = Form(...)):
        try:
            service.ai_rewrite_post(post_id, feedback.strip())
        except Exception as exc:  # noqa: BLE001
            notify("error", f"AI viết lại bài #{post_id} lỗi: {exc}")
        return RedirectResponse(f"/review/{post_id}", status_code=303)

    @app.post("/review/{post_id}/revert")
    def review_revert(post_id: int):
        review.revert_body(post_id)
        return RedirectResponse(f"/review/{post_id}", status_code=303)

    @app.post("/review/{post_id}/approve")
    def review_approve(post_id: int):
        review.approve(post_id)
        notify("info", f"Đã duyệt bài #{post_id}")
        return RedirectResponse(f"/review/{post_id}", status_code=303)

    @app.post("/review/{post_id}/reject")
    def review_reject(post_id: int, note: str = Form("")):
        review.reject(post_id, note=note or None)
        return RedirectResponse("/review?status=rejected", status_code=303)

    @app.post("/review/{post_id}/publish-now")
    def review_publish_now(post_id: int):
        post = review.get_post(post_id)
        if review.is_editable_status(post["status"]):
            review.approve(post_id)
        dry = get_config().dry_run
        try:
            result = sched.publish_post(post_id, dry_run=dry)
            if result.dry_run:
                notify("warning", f"⚠️ CHƯA đăng thật bài #{post_id}. Đang bật chế độ NHÁP "
                                  f"(dry-run) trong Cài đặt — tắt để đăng thật lên Facebook.")
            else:
                url = result.detail.get("url")
                link = f" Xem bài: {url}" if url else ""
                notify("info", f"✅ Đã đăng bài #{post_id} lên Facebook (mã: {result.external_id})."
                               f"{link}")
        except Exception as exc:  # noqa: BLE001
            notify("error", f"❌ Đăng bài #{post_id} lỗi: {exc}")
        return RedirectResponse(f"/review/{post_id}", status_code=303)

    @app.post("/review/{post_id}/schedule")
    def review_schedule(
        post_id: int,
        kind: str = Form("once"),
        run_at: str = Form(""),      # datetime-local cho ONCE
        time_of_day: str = Form(""),  # HH:MM cho DAILY/WEEKLY
        weekday: str = Form(""),
    ):
        post = review.get_post(post_id)
        if review.is_editable_status(post["status"]):
            review.approve(post_id)
        platform = Platform(post["platform"])
        k = ScheduleKind(kind)
        next_run = None
        if k == ScheduleKind.ONCE:
            if not run_at:
                notify("warning", "Chưa chọn thời điểm đăng.")
                return RedirectResponse(f"/review/{post_id}", status_code=303)
            local = datetime.fromisoformat(run_at).replace(tzinfo=_tz())
            next_run = local.astimezone(UTC)
        sched.add_schedule(
            k, platform, post_id=post_id,
            time_of_day=time_of_day or None,
            weekday=int(weekday) if weekday else None,
            next_run_at=next_run, mode=ScheduleMode.APPROVED_ONLY,
        )
        # đánh dấu SCHEDULED để UI hiển thị đúng (scheduler vẫn đăng được)
        with_status_scheduled(post_id)
        notify("info", f"Đã lên lịch đăng bài #{post_id}.")
        return RedirectResponse("/schedules", status_code=303)

    # ------------------------------------------------------------------ #
    # Lịch đăng
    # ------------------------------------------------------------------ #
    @app.get("/schedules", response_class=HTMLResponse)
    def schedules_page(request: Request):
        return templates.TemplateResponse(request, "schedules.html", {
            "request": request,
            "schedules": sched.list_schedules(),
            "cfg": get_config(),
            "kind_labels": {"once": "Một lần", "daily": "Hằng ngày",
                            "weekly": "Hằng tuần", "cron": "Nâng cao (cron)"},
        })

    @app.post("/schedules/{schedule_id}/toggle")
    def schedule_toggle(schedule_id: int):
        sched.toggle_schedule(schedule_id)
        return RedirectResponse("/schedules", status_code=303)

    @app.post("/schedules/{schedule_id}/delete")
    def schedule_delete(schedule_id: int):
        sched.remove_schedule(schedule_id)
        return RedirectResponse("/schedules", status_code=303)

    @app.post("/schedules/pause-all")
    def pause_all():
        cfg = get_config()
        cfg.pause_all_schedules = not cfg.pause_all_schedules
        save_config(cfg)
        state = "TẠM DỪNG" if cfg.pause_all_schedules else "BẬT LẠI"
        notify("warning", f"Đã {state} tất cả lịch đăng.")
        return RedirectResponse("/schedules", status_code=303)

    # ------------------------------------------------------------------ #
    # Cài đặt
    # ------------------------------------------------------------------ #
    @app.get("/settings", response_class=HTMLResponse)
    def settings_page(request: Request, checked: str = "", msg: str = ""):
        s = get_secrets()
        return templates.TemplateResponse(request, "settings.html", {
            "request": request, "cfg": get_config(), "secrets": s,
            "diag": service.diagnostics(),
            "default_topic": service.get_setting("default_topic", ""),
            "brand_hint": service.get_setting("brand_hint", ""),
            "checked": checked, "msg": msg,
            "fb_token_set": bool(s.fb_page_access_token),
        })

    @app.post("/settings/ai")
    def settings_ai(
        provider: str = Form(...),
        antigravity_model: str = Form(""),
        antigravity_cheap_model: str = Form(""),
        antigravity_timeout: int = Form(300),
    ):
        from ..env_writer import update_env

        allowed = {
            "antigravity_cli", "claude_cli", "gemini_cli", "codex_cli",
            "local", "claude", "openai", "gemini",
        }
        if provider not in allowed:
            notify("error", f"Nhà cung cấp AI không hợp lệ: {provider}")
            return RedirectResponse("/settings", status_code=303)

        cfg = get_config()
        cfg.llm.antigravity_cli.draft_model = antigravity_model.strip()
        cfg.llm.antigravity_cli.cheap_model = (
            antigravity_cheap_model.strip() or antigravity_model.strip()
        )
        cfg.llm.antigravity_cli.timeout_seconds = max(30, min(900, antigravity_timeout))
        save_config(cfg)
        update_env({"LLM_PROVIDER": provider})
        reload_secrets()
        label = "Google AI Ultra qua Antigravity CLI" if provider == "antigravity_cli" else provider
        if provider == "antigravity_cli":
            from ..antigravity_setup import setup_antigravity

            setup = setup_antigravity()
            if setup["ok"]:
                notify("info", f"Đã lưu cấu hình và xác nhận đăng nhập: {label}")
            else:
                notify(
                    "warning",
                    f"Đã lưu cấu hình {label}, nhưng chưa đăng nhập được: {setup['error']}",
                )
        else:
            notify("info", f"Đã lưu cấu hình AI: {label}")
        return RedirectResponse("/settings", status_code=303)

    @app.post("/settings/fb")
    def settings_fb(fb_page_id: str = Form(""), fb_page_access_token: str = Form("")):
        from ..env_writer import update_env

        updates = {}
        if fb_page_id.strip():
            updates["FB_PAGE_ID"] = fb_page_id.strip()
        if fb_page_access_token.strip():
            updates["FB_PAGE_ACCESS_TOKEN"] = fb_page_access_token.strip()
        if updates:
            update_env(updates)
            reload_secrets()
            notify("info", "Đã lưu kết nối Facebook (token được lưu cục bộ, không hiển thị lại).")
        return RedirectResponse("/settings", status_code=303)

    @app.post("/settings/general")
    def settings_general(
        timezone: str = Form("Asia/Ho_Chi_Minh"),
        dry_run: str = Form("on"),
        min_hours: int = Form(6),
        max_per_day: int = Form(3),
        default_topic: str = Form(""),
        brand_hint: str = Form(""),
    ):
        cfg = get_config()
        cfg.scheduler.timezone = timezone
        cfg.dry_run = dry_run == "on"
        cfg.scheduler.min_hours_between_posts = min_hours
        cfg.scheduler.max_posts_per_day_per_platform = max_per_day
        save_config(cfg)
        service.set_setting("default_topic", default_topic)
        service.set_setting("brand_hint", brand_hint)
        notify("info", "Đã lưu cài đặt chung.")
        return RedirectResponse("/settings", status_code=303)

    @app.post("/settings/check-ai")
    def check_ai():
        from ..content.llm import LLM

        try:
            out = LLM().complete(
                "Bạn là trợ lý ngắn gọn.", "Viết đúng 1 câu chào ngắn bằng tiếng Việt.",
                max_tokens=60,
            )
            msg = f"OK — AI trả lời: {out.strip()[:120]}"
        except Exception as exc:  # noqa: BLE001
            msg = f"LỖI: {str(exc)[:200]}"
        return RedirectResponse(f"/settings?checked=ai&msg={msg}", status_code=303)

    @app.api_route("/settings/antigravity-login", methods=["GET", "POST"])
    def antigravity_login():
        """Cho phép cả nút POST và mở URL trực tiếp trên trình duyệt local."""
        from ..antigravity_setup import setup_antigravity

        result = setup_antigravity(force=True)
        if result["ok"]:
            msg = "OK — Đã đăng nhập Google và chọn antigravity_cli"
        else:
            msg = f"LỖI: {result['error']}"[:220]
        return RedirectResponse(f"/settings?checked=ai&msg={msg}", status_code=303)

    @app.post("/settings/check-fb")
    def check_fb():
        from ..publishers.facebook_api import FacebookPagePublisher

        r = FacebookPagePublisher().check()
        msg = f"OK — Fanpage: {r['name']}" if r.get("ok") else f"LỖI: {r.get('error')}"
        return RedirectResponse(f"/settings?checked=fb&msg={msg}", status_code=303)

    # ------------------------------------------------------------------ #
    # Trang tĩnh: cam kết an toàn + hướng dẫn
    # ------------------------------------------------------------------ #
    @app.get("/safety", response_class=HTMLResponse)
    def safety(request: Request):
        return templates.TemplateResponse(request, "safety.html", {"request": request})

    @app.get("/help", response_class=HTMLResponse)
    def help_page(request: Request):
        return templates.TemplateResponse(request, "help.html", {"request": request})

    return app


def with_status_scheduled(post_id: int) -> None:
    """Đặt trạng thái bài = SCHEDULED (giữ nguyên external_id/dữ liệu khác)."""
    from ..db import session_scope
    from ..models import Post

    with session_scope() as s:
        p = s.get(Post, post_id)
        if p is not None and p.status in (PostStatus.APPROVED, PostStatus.NEEDS_REVIEW,
                                          PostStatus.DRAFT, PostStatus.REJECTED):
            p.status = PostStatus.SCHEDULED


# Đối tượng app mặc định cho `uvicorn fbauto.web.app:app`
app = create_app()
