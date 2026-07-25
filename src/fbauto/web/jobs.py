"""Job nền cho các tác vụ lâu (sinh bài) để không chặn request web.

Chạy trong thread; trạng thái lưu trong bộ nhớ tiến trình (app 1 người, 1 process).
UI hỏi /api/job/{id} định kỳ để hiện tiến trình 'đang viết…'.
"""

from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..enums import Language, PostLength, PostTone
from ..image_generation import (
    AntigravityImageGenerator,
    ImageGenerationRequest,
    image_locks,
)
from ..service import create_topic_and_generate

# Nhãn tiếng Việt cho từng bước sinh bài.
_STAGE_VI = {
    "outline": "Đang lập dàn ý…",
    "draft": "Đang viết bài…",
    "critique": "Đang tự chấm điểm…",
    "refine": "Đang cải thiện bài…",
    "refine_skip": "Bài đạt chất lượng — hoàn tất.",
    "image": "Đang tạo ảnh minh họa…",
}


@dataclass
class Job:
    id: str
    status: str = "running"  # running | done | error
    stage: str = "Đang chuẩn bị…"
    result: dict[str, Any] | None = None
    error: str | None = None
    log: list[str] = field(default_factory=list)
    kind: str = "post"
    post_id: int | None = None
    image_status: str | None = None


_JOBS: dict[str, Job] = {}
_LOCK = threading.Lock()


def get_job(job_id: str) -> Job | None:
    with _LOCK:
        return _JOBS.get(job_id)


def start_generate_job(
    title: str, *, brand_hint: str | None, language: Language,
    tone: PostTone, length: PostLength, generate_image: bool = False,
    image_aspect_ratio: str = "4:5", image_style: str = "auto",
    image_visual_brief: str = "",
) -> str:
    job_id = uuid.uuid4().hex[:12]
    job = Job(id=job_id)
    with _LOCK:
        _JOBS[job_id] = job

    def on_stage(kind: str, note: str = "") -> None:
        job.stage = _STAGE_VI.get(kind, kind)
        if note:
            job.log.append(f"{job.stage} ({note})")
        else:
            job.log.append(job.stage)

    def run() -> None:
        try:
            res = create_topic_and_generate(
                title, brand_hint=brand_hint, language=language,
                tone=tone, length=length, on_stage=on_stage,
            )
            job.post_id = res["post_id"]
            if generate_image:
                on_stage("image", "")
                _generate_image(
                    job, res["post_id"], image_aspect_ratio, image_style, image_visual_brief
                )
            job.result = res
            job.status = "done"
            job.stage = "Xong! Bài đã sẵn sàng để duyệt."
        except Exception as exc:  # noqa: BLE001
            job.status = "error"
            job.error = str(exc)
            job.stage = "Có lỗi khi viết bài."

    threading.Thread(target=run, daemon=True).start()
    return job_id


def _generate_image(
    job: Job, post_id: int, ratio: str, style: str, visual_brief: str,
    generator: AntigravityImageGenerator | None = None,
) -> None:
    from ..db import session_scope
    from ..models import Post, PostLog

    job.image_status = "running"
    with session_scope() as session:
        p = session.get(Post, post_id)
        if p is None:
            raise ValueError(f"Không tìm thấy bài #{post_id}")
        request = ImageGenerationRequest(
            post_id, p.image_prompt or p.body[:500], visual_brief[:500], ratio, style,
            p.topic.title if p.topic else "", p.topic.brand_hint if p.topic else "",
        )
        session.add(PostLog(post_id=post_id, event="image_generation_started",
                            detail={"ratio": ratio, "style": style}))
    result = (generator or AntigravityImageGenerator()).generate(request)
    with session_scope() as session:
        p = session.get(Post, post_id)
        if result.ok and p:
            old = p.image_path
            p.image_path = result.image_path
            session.add(PostLog(post_id=post_id, event="image_generation_succeeded",
                                detail={"message": result.user_message, "path": result.image_path}))
            if old and "-ai-" in Path(old).name and old != result.image_path:
                try:
                    Path(old).unlink(missing_ok=True)
                except OSError:
                    pass
            job.image_status = "succeeded"
        else:
            session.add(PostLog(post_id=post_id, event="image_generation_failed",
                                detail={"message": result.user_message,
                                        "code": result.error_code,
                                        "detail": result.technical_detail}))
            job.image_status = "failed"
            job.log.append("Bài đã tạo, ảnh chưa tạo được: " + result.user_message)


def start_image_job(
    post_id: int, *, aspect_ratio: str, style: str, visual_brief: str = ""
) -> str:
    job_id = uuid.uuid4().hex[:12]
    existing = image_locks.claim(post_id, job_id)
    if existing:
        return existing
    job = Job(id=job_id, kind="image", post_id=post_id, stage="Đang tạo ảnh…")
    with _LOCK:
        _JOBS[job_id] = job

    def run() -> None:
        try:
            _generate_image(job, post_id, aspect_ratio, style, visual_brief)
            job.result = {"post_id": post_id}
            job.status = "done"
            job.stage = "Đã hoàn tất tác vụ ảnh."
        except Exception as exc:  # noqa: BLE001
            job.status = "error"
            job.error = str(exc)
        finally:
            image_locks.release(post_id, job_id)

    threading.Thread(target=run, daemon=True).start()
    return job_id
