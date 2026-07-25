# FB Auto Poster

App desktop nhỏ chạy cục bộ: **nhập chủ đề → AI viết bài → bạn duyệt/sửa → hẹn giờ tự đăng
lên Facebook Fanpage**. AI viết bằng **CLI subscription chính hãng** (Google AI Ultra/ChatGPT/Claude),
**không cần API key, không tốn thêm tiền theo lượt**. Đăng Fanpage qua **Graph API** (an toàn).

> Bản nháp nội bộ — dự án cá nhân. Xem `PLAN.md` để biết kiến trúc & quyết định.

## Chạy nhanh

**Cách dễ nhất (macOS):** double-click `start.command`.
**Windows:** double-click `start.bat`.

Hai launcher sẽ tự dò và cài Antigravity CLI chính thức nếu máy chưa có. Ở lần chạy đầu,
launcher mở Google Sign-In, kiểm tra bằng một prompt ngắn rồi tự đặt
`LLM_PROVIDER=antigravity_cli`. Những lần sau bỏ qua bước đăng nhập. Có thể đăng nhập lại tại
**Cài đặt → Đăng nhập lại Google AI Ultra**.

**Bằng lệnh:**
```bash
uv sync
uv run fbauto init-db
uv run fbauto serve         # mở http://localhost:8791 (đổi port: --port 8642)
```

## Kết nối

1. **AI viết bài** — cài 1 trong 3 CLI và đăng nhập (không API key):
   - Google AI Ultra (cá nhân) → **Antigravity CLI** (`agy`) → provider
     `antigravity_cli` (khuyên dùng; Gemini CLI ngừng phục vụ tài khoản cá nhân từ 18/06/2026)
   - Claude CLI (`claude`) — gói Claude Pro/Max → provider `claude_cli`
   - Gemini CLI (`gemini`) — chỉ Enterprise/API cũ → provider `gemini_cli`
   - ChatGPT Codex CLI (`codex`) — gói ChatGPT Plus/Pro → provider `codex_cli`
   - Đặt provider trong **Cài đặt** hoặc `.env` (`LLM_PROVIDER=`).

### Google AI Ultra không API key

```bash
# macOS/Linux: cài CLI chính thức
curl -fsSL https://antigravity.google/cli/install.sh | bash

# đăng nhập bằng đúng tài khoản có Google AI Ultra
agy

# xem các model tài khoản được cấp (tùy chọn)
agy models
```

Sau đó vào **Cài đặt → Google AI Ultra — Antigravity CLI**, nên để model trống (Auto), lưu và
bấm **Kiểm tra kết nối AI**. “Ultra” là gói thuê bao; không cấu hình model giả định
`gemini-ultra`. App gọi chế độ headless chính thức `agy -p` và dùng phiên đăng nhập trong keyring
của hệ điều hành.
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
uv run fbauto setup-antigravity --force  # đăng nhập/cấu hình lại Google AI Ultra
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
