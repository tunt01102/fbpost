"""CLI cho FB Auto Poster (typer)."""

from __future__ import annotations

import typer
from rich import print as rprint

from .enums import Language, PostLength, PostTone

app = typer.Typer(add_completion=False, help="FB Auto Poster — CLI quản trị.")


@app.command("init-db")
def init_db_cmd() -> None:
    """Tạo thư mục dữ liệu + bảng SQLite."""
    from .db import init_db

    init_db()
    rprint("[green]✓[/green] Đã khởi tạo cơ sở dữ liệu.")


@app.command()
def serve(
    host: str = "127.0.0.1",
    port: int = 8791,  # port ít dùng (tránh 8000 hay bị app khác chiếm); đổi bằng --port
    open_browser: bool = typer.Option(True, "--open/--no-open", help="Tự mở trình duyệt"),
) -> None:
    """Chạy web server (mặc định http://localhost:8791; đổi bằng --port)."""
    import threading
    import webbrowser

    import uvicorn

    if open_browser:
        threading.Timer(1.5, lambda: webbrowser.open(f"http://{host}:{port}/")).start()
    rprint(f"[bold]FB Auto Poster[/bold] → http://{host}:{port}/")
    uvicorn.run("fbauto.web.app:app", host=host, port=port, log_level="info")


@app.command()
def generate(
    title: str,
    tone: str = "sharing",
    length: str = "medium",
    brand: str = typer.Option("", help="Mô tả thương hiệu/giọng"),
) -> None:
    """Sinh một bài từ chủ đề (in kết quả)."""
    from .db import init_db
    from .service import create_topic_and_generate

    init_db()
    res = create_topic_and_generate(
        title, brand_hint=brand or None, language=Language.VI,
        tone=PostTone(tone), length=PostLength(length),
    )
    rprint(f"[green]✓[/green] Đã tạo bài #{res['post_id']} — điểm {res['score']}, "
           f"qua cổng chất lượng: {res['gate_passed']}")
    if res["reasons"]:
        rprint(f"[yellow]Cần sửa:[/yellow] {res['reasons']}")
    if res["warnings"]:
        rprint(f"[yellow]Lưu ý:[/yellow] {res['warnings']}")


@app.command("check-ai")
def check_ai() -> None:
    """Thử gọi AI viết 1 câu để kiểm tra kết nối."""
    from .content.llm import LLM

    try:
        out = LLM().complete("Bạn là trợ lý ngắn gọn.",
                             "Viết đúng 1 câu chào bằng tiếng Việt.", max_tokens=60)
        rprint(f"[green]✓ OK[/green] — {out.strip()[:150]}")
    except Exception as exc:  # noqa: BLE001
        rprint(f"[red]✗ LỖI[/red] — {exc}")
        raise typer.Exit(1) from exc


@app.command("check-fb")
def check_fb() -> None:
    """Kiểm tra kết nối Facebook Fanpage (Graph API)."""
    from .publishers.facebook_api import FacebookPagePublisher

    r = FacebookPagePublisher().check()
    if r.get("ok"):
        rprint(f"[green]✓ OK[/green] — Fanpage: {r['name']}")
    else:
        rprint(f"[red]✗ LỖI[/red] — {r.get('error')}")
        raise typer.Exit(1)


@app.command("run-scheduler")
def run_scheduler() -> None:
    """Chạy riêng bộ hẹn giờ (chặn). Thường web đã tự chạy — chỉ dùng khi tách process."""
    from .db import init_db
    from .scheduler.service import SchedulerService

    init_db()
    SchedulerService().start(block=True)


@app.command()
def diagnostics() -> None:
    """In chẩn đoán (đèn xanh/đỏ)."""
    from .db import init_db
    from .service import diagnostics as diag

    init_db()
    rprint(diag())


if __name__ == "__main__":
    app()
