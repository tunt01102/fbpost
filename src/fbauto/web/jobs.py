"""Job nền cho các tác vụ lâu (sinh bài) để không chặn request web.

Chạy trong thread; trạng thái lưu trong bộ nhớ tiến trình (app 1 người, 1 process).
UI hỏi /api/job/{id} định kỳ để hiện tiến trình 'đang viết…'.
"""

from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field
from typing import Any

from ..enums import Language, PostLength, PostTone
from ..service import create_topic_and_generate

# Nhãn tiếng Việt cho từng bước sinh bài.
_STAGE_VI = {
    "outline": "Đang lập dàn ý…",
    "draft": "Đang viết bài…",
    "critique": "Đang tự chấm điểm…",
    "refine": "Đang cải thiện bài…",
    "refine_skip": "Bài đạt chất lượng — hoàn tất.",
}


@dataclass
class Job:
    id: str
    status: str = "running"  # running | done | error
    stage: str = "Đang chuẩn bị…"
    result: dict[str, Any] | None = None
    error: str | None = None
    log: list[str] = field(default_factory=list)


_JOBS: dict[str, Job] = {}
_LOCK = threading.Lock()


def get_job(job_id: str) -> Job | None:
    with _LOCK:
        return _JOBS.get(job_id)


def start_generate_job(
    title: str, *, brand_hint: str | None, language: Language,
    tone: PostTone, length: PostLength,
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
            job.result = res
            job.status = "done"
            job.stage = "Xong! Bài đã sẵn sàng để duyệt."
        except Exception as exc:  # noqa: BLE001
            job.status = "error"
            job.error = str(exc)
            job.stage = "Có lỗi khi viết bài."

    threading.Thread(target=run, daemon=True).start()
    return job_id
