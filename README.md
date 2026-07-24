# FB Auto Poster

App desktop nhỏ chạy cục bộ: **nhập chủ đề → AI viết bài → bạn duyệt/sửa → hẹn giờ tự đăng
lên Facebook Fanpage**. AI viết bằng **CLI subscription chính hãng** (ChatGPT/Gemini/Claude),
**không cần API key, không tốn thêm tiền theo lượt**. Đăng Fanpage qua **Graph API** (an toàn).

> Bản nháp nội bộ — dự án cá nhân. Xem `PLAN.md` để biết kiến trúc & quyết định.

## Chạy nhanh

**Cách dễ nhất (macOS):** double-click `start.command`.
**Windows:** double-click `start.bat`.

**Bằng lệnh:**
```bash
uv sync
uv run fbauto init-db
uv run fbauto serve         # mở http://localhost:8000
```

## Kết nối

1. **AI viết bài** — cài 1 trong 3 CLI và đăng nhập (không API key):
   - Claude CLI (`claude`) — gói Claude Pro/Max → provider `claude_cli`
   - Gemini CLI (`gemini`) — tài khoản Google → provider `gemini_cli`
   - ChatGPT Codex CLI (`codex`) — gói ChatGPT Plus/Pro → provider `codex_cli`
   - Đặt provider trong **Cài đặt** hoặc `.env` (`LLM_PROVIDER=`).
2. **Facebook Fanpage** — dán **Page ID** + **Page Access Token** trong **Cài đặt → Kết nối Facebook**
   (xem trang **Hướng dẫn** trong app). Token lưu cục bộ (Keychain/`.env`), không gửi đi đâu.

## An toàn & mặc định

- **Mặc định BẮT BUỘC người duyệt** — không tự đăng khi chưa duyệt.
- **Chế độ nháp (`dry_run`) bật sẵn** — thao tác "đăng" chỉ chạy thử. Tắt trong Cài đặt để đăng thật.
- Chống trùng (`external_id`), chống spam (giãn cách + trần bài/ngày), công tắc **Tạm dừng tất cả lịch**.
- Toàn bộ dữ liệu lưu **trên máy bạn** (`data/app.sqlite`).

## Lệnh CLI

```bash
uv run fbauto init-db          # tạo DB
uv run fbauto serve            # chạy web
uv run fbauto generate "chủ đề ..."   # sinh 1 bài (in kết quả)
uv run fbauto check-ai         # kiểm tra kết nối AI
uv run fbauto check-fb         # kiểm tra kết nối Facebook
uv run fbauto diagnostics      # đèn xanh/đỏ
uv run pytest                  # chạy test
```

## Kiến trúc (tóm tắt)

- `content/llm.py` — adapter LLM (CLI subscription / API / local) + fallback.
- `content/generator.py` — outline → draft → critique → refine.
- `validation/gates.py` — cổng chất lượng (rỗng/quá dài/PII/trùng/sáo rỗng).
- `review/service.py` — xem/sửa/duyệt/từ chối + AuditLog + đồng hồ review.
- `scheduler/service.py` — hẹn giờ (APScheduler), idempotent, chống spam, catch-up an toàn.
- `publishers/` — `facebook_api` (Graph API, khuyến nghị) + `facebook_browser` (Playwright, tùy chọn).
- `web/` — FastAPI + Jinja2, giao diện tiếng Việt.
