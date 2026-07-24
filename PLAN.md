# KẾ HOẠCH CHI TIẾT — App "FB Auto Poster" (tự sinh & hẹn giờ đăng Facebook bằng AI, không dùng API)

> **Trạng thái tài liệu:** BẢN NHÁP NỘI BỘ — cần người review trước khi dùng chính thức.
> **Người nhận:** tu.nguyen@block8.ai · **Ngày:** 2026-07-24
> **Đối tượng người dùng cuối của app:** người **không rành IT** (chủ shop, người làm dịch vụ tự do…).
> **Dự án tham khảo (tái sử dụng code):** `/Users/macbook/PycharmProjects/fb-linkedin-auto`
> **Thư mục dự án mới:** `/Users/macbook/PycharmProjects/fbAuto`

---

## 0. TÓM TẮT NHANH (đọc cái này trước)

App desktop nhỏ, chạy trên máy cá nhân (macOS/Windows), mở giao diện trong trình duyệt tại `http://localhost:8000`. App giúp người dùng:

1. **Nhập chủ đề** muốn viết (VD: "khuyến mãi cà phê mùa hè").
2. **AI tự viết bài** — dùng tài khoản **trả phí sẵn có** của ChatGPT / Gemini / Claude qua **CLI (dòng lệnh chính hãng)**, **KHÔNG cần API key, KHÔNG tốn thêm tiền theo lượt**.
3. **Xem trước, duyệt, chỉnh sửa** bài như một biên tập viên chuyên nghiệp.
4. **Hẹn giờ** → app **tự động đăng** lên Facebook/Fanpage đúng giờ đã chọn.

### Hai quyết định kỹ thuật quan trọng (và lý do)

| Vấn đề | Khuyến nghị | Vì sao |
|---|---|---|
| "Dùng AI không qua API" | **CLI subscription chính hãng** (`claude`, `gemini`, `codex`) đăng nhập bằng tài khoản Pro/Plus | Ổn định, **đúng luật (ToS)**, không tốn thêm tiền, **đã có sẵn trong code tham khảo** (`content/llm.py`). KHÔNG scrape web chat.openai.com/gemini/claude.ai (vi phạm ToS, dễ hỏng, dễ bị khoá). |
| Đăng Facebook Fanpage | **Ưu tiên: Graph API bằng Page Access Token** (dán token, không lập trình). **Tùy chọn: Playwright** (đăng nhập 1 lần) | Đăng qua **Fanpage + Page token an toàn hơn nhiều**, gần như không bị khoá. Playwright profile cá nhân **vi phạm ToS Facebook, dễ bị khoá tài khoản** — chỉ dùng khi hiểu rõ rủi ro. |

> ⚠️ **CẢNH BÁO TUÂN THỦ (Block8.ai):** Tự động hoá **profile Facebook cá nhân** và **scrape giao diện web** của ChatGPT/Gemini/Claude **vi phạm Điều khoản dịch vụ** của các nền tảng và có thể dẫn tới **khoá tài khoản vĩnh viễn**. Plan này ưu tiên các đường **hợp lệ** (Fanpage + Page token, CLI chính hãng). Không xử lý credential/token thật trong tài liệu này; token là bí mật, lưu trong Keychain/file `.env` cục bộ, **không chia sẻ**.

---

## 1. PHẠM VI & MỤC TIÊU

### 1.1 Yêu cầu gốc (từ người đặt hàng)
1. Tự động sinh bài đăng Facebook/Fanpage bằng Gemini/ChatGPT/Claude — **không qua API**.
2. Chọn lịch → tự động đăng ở chế độ hẹn giờ.
3. Chế độ review + chỉnh sửa chuyên nghiệp.
4. Chủ đề do người dùng thiết lập.
5. App chạy độc lập, dễ sử dụng.
6. Lập **hội đồng thẩm định** (UIUX, PO, Fullstack, QA, End User) để review/thiết kế/cải thiện/thực hiện/test và giao thành phẩm.
7. Hướng dẫn **chi tiết** cách lấy thông tin tài khoản Facebook/Fanpage và cấu hình Gemini/ChatGPT/Claude (không qua API) cho người **không rành IT**.

### 1.2 Ngoài phạm vi (v1 KHÔNG làm — để sau)
- Đăng đa nền tảng (LinkedIn/X/Instagram) — code tham khảo có sẵn nhưng **hoãn**.
- Tự sinh **ảnh/video** AI — hoãn (v1 cho phép **đính kèm ảnh có sẵn** từ máy).
- Trả lời bình luận tự động, phân tích engagement, A/B testing, học tự động (learning bandit) — hoãn.
- Nhiều người dùng / đăng nhập / cloud — app là **1 người, chạy cục bộ**.

---

## 2. KIẾN TRÚC TỔNG THỂ

```
┌───────────────────────────────────────────────────────────────┐
│  Trình duyệt (người dùng)  →  http://localhost:8000            │
│  Giao diện web: FastAPI + Jinja2 + HTMX + Alpine.js            │
└───────────────┬───────────────────────────────────────────────┘
                │ (gọi hàm nội bộ)
   ┌────────────┴───────────────────────────────────────────────┐
   │  LÕI ỨNG DỤNG (Python, package src/fbauto)                  │
   │                                                             │
   │  ┌─────────────┐  ┌──────────────┐  ┌────────────────────┐  │
   │  │ Sinh bài    │  │ Review/Sửa   │  │ Lịch (Scheduler)   │  │
   │  │ generator + │  │ review/      │  │ APScheduler        │  │
   │  │ llm (CLI)   │  │ service.py   │  │ scheduler/service  │  │
   │  └──────┬──────┘  └──────┬───────┘  └─────────┬──────────┘  │
   │         │                │                    │             │
   │  ┌──────┴────────────────┴────────────────────┴──────────┐ │
   │  │  DB: SQLite (SQLAlchemy + Alembic)  data/app.sqlite    │ │
   │  └────────────────────────────────────────────────────────┘│
   │         │                                     │             │
   │  ┌──────┴───────┐                    ┌────────┴──────────┐  │
   │  │ LLM provider │                    │ Publisher         │  │
   │  │ claude_cli   │                    │ facebook_page_api │  │
   │  │ gemini_cli   │                    │  (Graph API) HOẶC │  │
   │  │ codex_cli    │                    │ facebook_browser  │  │
   │  │ (subprocess) │                    │  (Playwright)     │  │
   │  └──────┬───────┘                    └────────┬──────────┘  │
   └─────────┼───────────────────────────────────┼─────────────┘
             ▼                                     ▼
   CLI chính hãng đã đăng nhập            Facebook / Fanpage
   (Claude Pro / ChatGPT Plus /           (Graph API hoặc trình
    Gemini) — KHÔNG API key                duyệt tự động)
```

**Nguyên tắc:** tách **logic thuần** (test được) khỏi **I/O** (CLI, mạng, trình duyệt) — đúng như dự án tham khảo đã làm (VD `scheduler/service.py` tách `publish_post` khỏi APScheduler).

---

## 3. BẢN ĐỒ TÁI SỬ DỤNG CODE (từ `fb-linkedin-auto`)

Mục tiêu: **sao chép & lược bớt**, không viết lại từ đầu. Package đổi tên `social_poster` → `fbauto`.

### 3.1 Tái sử dụng gần như nguyên vẹn ✅
| Module nguồn | Vai trò | Ghi chú |
|---|---|---|
| `content/llm.py` | **Trái tim "không API"** — provider `claude_cli`/`gemini_cli`/`codex_cli` gọi CLI qua subprocess | Giữ nguyên; bỏ nhánh API trả phí (claude/openai/gemini API) cho gọn, hoặc giữ làm fallback nâng cao |
| `config.py` | Cấu hình `Secrets` (.env) + `settings.yaml`; đã có sẵn `ClaudeCliConfig`, `CliProviderConfig`, `_gemini_cli_default`, `_codex_cli_default` | Cắt bớt cấu hình LinkedIn/X/video/RAG/research |
| `scheduler/service.py` | Hẹn giờ đăng, chống trùng (`external_id`), chống spam (`frequency cap`, `daily cap`), retry, `coalesce`/`misfire_grace_time` (máy ngủ dậy không đăng dồn) | Bỏ job LinkedIn/X token refresh; giữ FB |
| `scheduler/calendar.py` | Tính lịch/khung giờ | Giữ |
| `review/service.py` | Xem/sửa/duyệt/từ chối bài + `AuditLog`; đồng hồ thời gian review | Giữ; đây là nền của "review chuyên nghiệp" |
| `db.py`, `models.py`, `enums.py` | ORM + trạng thái bài (`DRAFT`→`NEEDS_REVIEW`→`APPROVED`→`SCHEDULED`→`PUBLISHED`/`FAILED`) | Cắt bảng thừa (Reply, Comment metrics…) nếu muốn gọn |
| `publishers/base.py`, `publishers/__init__.py` (`get_publisher`) | Giao diện Publisher chung + factory | Giữ |
| `publishers/facebook_api.py` | Đăng Fanpage qua **Graph API + Page token** (đường **khuyến nghị**) | Giữ làm publisher chính |
| `publishers/facebook_browser.py` | Đăng qua **Playwright** (`save_login_state()` lưu session) | Giữ làm tùy chọn; **mở rộng để đăng lên Fanpage** (hiện chỉ profile cá nhân) |
| `web/` (FastAPI + HTMX + Alpine + templates + help partials) | Toàn bộ khung UI, kể cả các trang **hướng dẫn setup** `help/_facebook.html`, `help/_llm.html` | Giữ khung, cắt trang thừa (analytics, engagement, projects…) |
| `observability/notify.py` | Thông báo lỗi/cảnh báo | Giữ (đổi sang thông báo trên UI + desktop notification) |
| `content/generator.py`, `content/prompts.py`, `content/schemas.py`, `content/editor.py` | Sinh bài + prompt + schema + biên tập lại theo góp ý | Giữ; đơn giản hoá cho FB một nền tảng |
| `secrets_store.py`, `env_writer.py` | Lưu token vào Keychain / ghi `.env` an toàn từ UI | Giữ — quan trọng cho "người không rành IT nhập token qua form" |
| `validation/gates.py` | Cổng chất lượng (bài rỗng/quá dài/thiếu…) | Giữ, tinh gọn theo giới hạn Facebook |

### 3.2 Cần sửa 🔧
- `publishers/facebook_browser.py`: hiện `publish()` chỉ đăng **profile cá nhân**. Cần thêm luồng **chọn Fanpage** → điều hướng tới trang Fanpage → đăng. Thêm `delete()` nếu cần gỡ bài.
- `content/llm.py`: có thể lược các provider API trả phí để giao diện đơn giản (chỉ để lại 3 CLI + `local` làm fallback).
- `config.py`: cắt cấu hình không dùng (LinkedIn, X, video, comfyui, research, RAG) để `settings.yaml` gọn, dễ đọc.
- `scheduler/service.py`: bỏ `token_refresh_job`, `poll_metrics_job`, `fetch_comments_job` (v1 không cần) hoặc để tắt.

### 3.3 Bỏ hẳn cho v1 ❌
`analytics/*`, `engagement/*`, `images/*`, `video/*`, `sources/*` (research), `strategy/*`, `memory/*` (learning), `crm.py`, `projects/*`, `publishers/linkedin_*`, `publishers/x_api.py`, `mcp_server.py` (trừ khi muốn cho phép Claude Code chấm điểm bài — nâng cao).

---

## 4. GIẢI THÍCH SÂU: "DÙNG AI KHÔNG QUA API" HOẠT ĐỘNG THẾ NÀO

Đây là điểm mấu chốt và cũng dễ hiểu nhầm. Có **2 cách** để "không dùng API":

### Cách A — CLI chính hãng đăng nhập bằng subscription ✅ **(KHUYẾN NGHỊ)**
Các hãng đều phát hành **công cụ dòng lệnh (CLI) chính hãng** mà bạn **đăng nhập bằng chính tài khoản trả phí** (không phải API key):

| Nhà cung cấp | CLI | Đăng nhập bằng | Gói cần |
|---|---|---|---|
| **Claude (Anthropic)** | `claude` (Claude Code) | Tài khoản Claude | Claude **Pro/Max** |
| **ChatGPT (OpenAI)** | `codex` (Codex CLI) | "Sign in with ChatGPT" | ChatGPT **Plus/Pro** |
| **Gemini (Google)** | `gemini` (Gemini CLI) | Tài khoản Google | Free / **AI Pro** |

App gọi các CLI này bằng `subprocess` (đã cài sẵn trong `content/llm.py`), truyền chủ đề + hướng dẫn, nhận về bài viết. **Không API key, không tính tiền theo lượt** (đã bao trong gói thuê bao), ổn định vì là công cụ chính hãng.

Ví dụ lệnh thực tế (code tham khảo dựng sẵn):
- Claude: `claude -p "<đề bài>" --system-prompt "<vai trò>" --model <model> --output-format text`
- Gemini: `gemini --skip-trust -m <model> -p "<đề bài>"`
- ChatGPT: `codex exec -m <model> "<đề bài>"`

Nếu một CLI lỗi/không cài, hệ thống **tự chuyển (fallback)** sang cái khác hoặc model local (`content/llm.py::_run`).

### Cách B — Tự động hoá trình duyệt web chat (Playwright scrape) ❌ **(KHÔNG khuyến nghị)**
Điều khiển trình duyệt mở `chat.openai.com` / `gemini.google.com` / `claude.ai`, gõ câu hỏi, copy câu trả lời.
**Nhược điểm:** vi phạm ToS của các web đó; giao diện thay đổi là hỏng; dễ bị chặn/khoá; phải xử lý đăng nhập + Cloudflare + captcha. → **Chỉ nêu để tham khảo, không đưa vào v1.**

> **Kết luận:** v1 dùng **Cách A**. Đây cũng là cách "không qua API" mà code tham khảo đã hỗ trợ đầy đủ.

---

## 5. LUỒNG NGHIỆP VỤ (end-to-end)

```
Người dùng nhập CHỦ ĐỀ
        │
        ▼
[Sinh bài] AI (CLI) viết nháp  → lưu DB trạng thái NEEDS_REVIEW
        │
        ▼
[Review chuyên nghiệp]  người dùng xem trước (đúng như Facebook hiển thị),
        │                chỉnh sửa (hook/nội dung/hashtag/CTA), hoặc bấm
        │                "AI viết lại theo góp ý" (content/editor.py)
        ▼
Bấm DUYỆT → trạng thái APPROVED
        │
        ▼
[Hẹn giờ] chọn ngày/giờ (hoặc lịch lặp lại) → trạng thái SCHEDULED
        │
        ▼  (đến giờ, APScheduler kích hoạt)
[Tự đăng] publish_post(): kiểm tra chống trùng + chống spam → đăng lên
        │                  Fanpage (Graph API) hoặc trình duyệt
        ▼
PUBLISHED (lưu external_id)  — lỗi thì FAILED + thông báo, cho đăng lại (retry_post)
```

**Chế độ hẹn giờ** dùng lại nguyên `scheduler/service.py`:
- `ScheduleKind`: `ONCE` (một lần), `DAILY`, `WEEKLY`, `CRON` (nâng cao).
- **Chính sách lịch lỡ (máy ngủ/tắt)** *(chốt sau hội đồng — PO + QA):* dùng `coalesce=True` + `misfire_grace_time` để **không đăng dồn**; nhưng với bài **quá hạn đáng kể**, KHÔNG tự đăng âm thầm → hiện hộp thoại **"Bài này đã lỡ giờ — Đăng ngay / Đổi giờ / Huỷ?"**. Chỉ tự đăng khi còn trong ngưỡng an toàn ngắn.
- Chống trùng: nếu bài đã có `external_id` thì không đăng lại.
- Chống spam: `min_hours_between_posts`, `max_posts_per_day_per_platform`.
- Múi giờ: cấu hình `scheduler.timezone` (đổi mặc định `Australia/Sydney` → `Asia/Ho_Chi_Minh`).

**Chế độ tự sinh + tự đăng (tùy chọn nâng cao):** `ScheduleMode.AUTO` / `GEN_REVIEW` — đến giờ tự sinh bài mới từ hàng chờ chủ đề. Mặc định **BẮT BUỘC người duyệt** (`review.require_human_approval = True`) để người dùng luôn kiểm soát.

---

## 6. THIẾT KẾ UI/UX (cho người KHÔNG rành IT)

### 6.1 Sitemap tối giản (≤5 mục)
1. **Trang chủ / Bảng tin** — tóm tắt: bài chờ duyệt, bài đã lên lịch, bài đã đăng; nút lớn **"➕ Tạo bài mới"**.
2. **Tạo bài** — nhập/chọn **chủ đề**, chọn giọng văn, bấm **"Nhờ AI viết"**.
3. **Duyệt & Sửa** — danh sách bài nháp; xem trước giống Facebook; sửa; **Duyệt** / **AI viết lại** / **Bỏ**.
4. **Lịch đăng** — xem lịch dạng calendar; đặt/sửa giờ đăng; bật/tắt.
5. **Cài đặt** — kết nối AI (đăng nhập CLI), kết nối Facebook/Fanpage, chủ đề mặc định. **Có nút "Kiểm tra kết nối"** cho mỗi mục.

### 6.2 Nguyên tắc UX bắt buộc
- **Ngôn ngữ đời thường, không thuật ngữ.** Đổi tên khái niệm:
  - "API/token" → "**Chìa khoá kết nối**" / "**Kết nối Facebook**"
  - "CLI/subscription" → "**Kết nối tài khoản AI (ChatGPT/Gemini/Claude)**"
  - "session/storage_state" → "**Ghi nhớ đăng nhập**"
  - "cron/schedule" → "**Lịch đăng**"
  - "publish" → "**Đăng bài**"
- **Luôn xem trước** bài đúng như Facebook sẽ hiển thị trước khi đăng.
- **Không bao giờ tự đăng khi chưa duyệt** (mặc định). Có công tắc lớn "**Tạm dừng tất cả lịch đăng**".
- **Đếm ngược trước khi đăng** *(End User)*: trước giờ đăng ít phút, hiện thông báo "⏰ 15 phút nữa sẽ đăng bài này — bấm **Huỷ** nếu không muốn". Cho người dùng chốt chặn cuối.
- **Báo kết quả rõ ràng** *(UX + QA)*: sau khi đăng, hiện "✅ Đã đăng — [Xem bài]" (kèm link thật) hoặc "❌ Đăng lỗi — [Thử lại]". Không bao giờ để trạng thái mập mờ.
- **Mọi hành động có thể Hoàn tác / Xác nhận lại** (đặc biệt: xoá, đăng ngay).
- **Trạng thái rõ ràng bằng màu + chữ Việt**: Nháp / Chờ duyệt / Đã duyệt / Đã lên lịch / Đã đăng / Lỗi.
- **Thông báo lỗi bằng tiếng Việt dễ hiểu + gợi ý cách sửa** (VD: "Mất kết nối Facebook — hãy vào Cài đặt bấm Kết nối lại").

### 6.3 Onboarding lần đầu (wizard 5 bước)
1. Chào mừng → chọn ngôn ngữ (mặc định Tiếng Việt).
2. **Kết nối AI**: hướng dẫn cài & đăng nhập 1 trong 3 CLI (có nút "Kiểm tra" → app tự chạy thử 1 câu).
3. **Kết nối Facebook/Fanpage**: chọn cách (Fanpage-token *khuyến nghị* / trình duyệt) → làm theo hướng dẫn có ảnh.
4. **Đặt chủ đề** đầu tiên + giọng văn thương hiệu.
5. **"Khoảnh khắc thành công"** *(UX)*: tạo & xem trước ngay 1 bài demo để người dùng thấy giá trị trước khi cấu hình thêm.

*Kèm màn hình **Đồng ý rủi ro (Disclaimer)** một lần khi cài (PO): nêu rõ rủi ro ToS, giới hạn tần suất đăng, và cam kết dữ liệu lưu cục bộ.*

### 6.4 Trang "Cam kết an toàn" (trấn an người dùng — End User)
Một trang ngắn, ngôn ngữ đời thường, trả lời đúng 3 nỗi sợ lớn nhất:
- **"Có an toàn với Facebook không?"** → Dùng đường chính hãng (Graph API cho Fanpage); mặc định bạn duyệt trước khi đăng; giới hạn tần suất để không giống spam.
- **"Có tốn thêm tiền không?"** → Không tính tiền theo lượt: app dùng gói AI **bạn đã trả hằng tháng**, không nhập thẻ, không API tính phí.
- **"Dữ liệu của tôi lưu ở đâu?"** → Toàn bộ lưu **trên máy bạn**; token/mật khẩu không gửi đi đâu, không đưa vào công cụ AI, không hiển thị lại.
- Kèm **video hướng dẫn tiếng Việt 3–5 phút**, ảnh khoanh đỏ từng bước, checklist, và kênh **Zalo/điện thoại hỗ trợ** khi kẹt.

---

## 7. HƯỚNG DẪN CHI TIẾT CHO NGƯỜI KHÔNG RÀNH IT (đưa vào app + tài liệu in kèm)

> Nguyên tắc trình bày: **mỗi bước 1 việc, kèm ảnh chụp màn hình thật, có checklist ✅, có nút "Kiểm tra" trong app**. Kèm 1 video ngắn 3–5 phút. Tránh mọi từ kỹ thuật; nếu buộc dùng thì giải thích ngay trong ngoặc.

### 7.1 Cài đặt app (1 lần)
- **macOS:** tải file `.dmg` → kéo app vào Applications → mở (lần đầu chuột phải → Open để qua cảnh báo). 
- **Windows:** tải `.exe`/thư mục zip → chạy `FBAutoPoster.exe`.
- App tự mở trình duyệt tới `http://localhost:8000`. (Đóng gói bằng PyInstaller/briefcase — xem §9.)

### 7.2 Kết nối AI viết bài (chọn 1 trong 3 — chỉ cần 1)

**A. Dùng ChatGPT (bạn đang có gói ChatGPT Plus):**
1. Cài **Codex CLI** của OpenAI (app kèm nút "Hướng dẫn cài" mở trang tải + copy sẵn lệnh).
2. Mở app → **Cài đặt → Kết nối AI → ChatGPT → "Đăng nhập"**. Một cửa sổ trình duyệt hiện ra → đăng nhập tài khoản ChatGPT như bình thường.
3. Bấm **"Kiểm tra"**. App tự nhờ AI viết 1 câu thử. Thấy chữ "✅ Kết nối OK" là xong.

**B. Dùng Gemini (tài khoản Google):**
1. Cài **Gemini CLI**. 2. **Cài đặt → Kết nối AI → Gemini → "Đăng nhập"** bằng tài khoản Google. 3. Bấm **"Kiểm tra"**.

**C. Dùng Claude (gói Claude Pro/Max):**
1. Cài **Claude CLI**. 2. **Cài đặt → Kết nối AI → Claude → "Đăng nhập"**. 3. Bấm **"Kiểm tra"**.

> **Điểm cần rõ với người dùng:** *"Bạn không cần lấy 'API key' hay nhập thẻ tín dụng ở đây. App chỉ mượn tài khoản AI bạn đã trả tiền hằng tháng để viết bài giúp bạn."*

*(Với người thực sự ngại cài CLI: đội kỹ thuật có thể chuẩn bị sẵn 1 bản cài "tất-cả-trong-một" có kèm CLI, để người dùng chỉ đăng nhập.)*

### 7.3 Lấy thông tin Facebook / Fanpage

> **Khuyến nghị mạnh:** dùng **Fanpage** (Trang) chứ **không** dùng profile cá nhân, để **an toàn tài khoản** và **đúng luật Facebook**.

**Cách 1 — Fanpage bằng "Chìa khoá kết nối" (Page Access Token) — KHUYẾN NGHỊ, an toàn:**
Người dùng phần lớn chỉ cần làm 1 lần, và app dẫn từng bước (nội dung dựa trên `help/_facebook.html` có sẵn):
1. Bạn phải là **Quản trị viên** của Fanpage.
2. Vào **developers.facebook.com/apps** → **Create App** → chọn **Business**. *(App có nút mở sẵn link.)*
3. Vào **Graph API Explorer** → chọn app của bạn → **Generate Access Token** → tick các quyền: `pages_show_list`, `pages_read_engagement`, `pages_manage_posts`, `pages_manage_engagement`.
4. Đổi sang **token dài hạn** rồi lấy **Page ID + Page Token** (app hiển thị đường link bấm-là-ra, kèm hình minh hoạ).
5. **Dán** Page ID + Page Token vào ô trong app → bấm **"Kiểm tra"** (app gọi thử, hiện tên Fanpage nếu OK).

> ⚠️ *Muốn đăng cho Fanpage của người khác/ngoài tài khoản dev → Facebook yêu cầu "App Review". Với nhu cầu tự đăng lên Fanpage của chính bạn thì thường không cần.*
> 🔒 *Token là bí mật — app lưu an toàn trong máy bạn (Keychain/`.env`), không gửi đi đâu, không hiển thị lại đầy đủ.*

**Cách 2 — Đăng bằng trình duyệt (Playwright) — dễ setup hơn nhưng rủi ro hơn:**
1. **Cài đặt → Kết nối Facebook → "Đăng nhập bằng trình duyệt"**. Cửa sổ trình duyệt mở ra.
2. Đăng nhập Facebook như bình thường (kể cả 2FA), chọn Fanpage muốn đăng.
3. App **ghi nhớ đăng nhập** (lưu `storage_state`) để lần sau tự đăng.
> ⚠️ **Rủi ro:** Facebook có thể coi đây là hành vi tự động → **cảnh báo/khoá tài khoản**. Nên đăng với **tần suất thấp, giờ tự nhiên**, ưu tiên Cách 1.

### 7.4 Đặt chủ đề
- **Cài đặt → Chủ đề**: nhập danh sách chủ đề (VD: "mẹo chăm da mùa hè", "ưu đãi cuối tuần"), giọng văn (thân thiện/chuyên nghiệp/hài hước), và (tùy chọn) mô tả thương hiệu để AI viết đúng chất.

---

## 8. CHẾ ĐỘ "REVIEW + CHỈNH SỬA CHUYÊN NGHIỆP"

Dựa trên `review/service.py` + templates `review*.html`. **Bố cục 2 cột** *(UX)*: **trái** = xem trước y hệt Facebook; **phải** = ô sửa + nút nhanh ("Viết lại", "Ngắn gọn hơn", "Thêm emoji", "Đổi giọng văn"). Mặc định đơn giản; tính năng nâng cao (hashtag, giờ tối ưu, biến thể A/B) giấu sau nút "Nâng cao". Mỗi lần AI viết lại → giữ bản cũ, có nút **"Quay lại bản trước"**. Ba nút chốt: **Duyệt & hẹn giờ** / **Lưu nháp** / **Bỏ**. Bao gồm:
- **Xem trước trung thực** (preview giống bố cục Facebook: ảnh đại diện, tên trang, nội dung, hashtag, CTA).
- **Sửa từng phần**: tiêu đề móc (hook), nội dung, hashtag, CTA, chú thích ảnh (alt-text). (`review.edit()`)
- **AI viết lại theo góp ý**: ô "Bạn muốn sửa gì?" → gọi `content/editor.py` để AI tinh chỉnh (giữ ý, đổi giọng, rút gọn…).
- **Cổng chất lượng tự động** (`validation/gates.py`): cảnh báo bài quá dài (giới hạn Facebook), rỗng, thiếu CTA, trùng nội dung gần đây.
- **Nhật ký thao tác** (`AuditLog`): ghi ai sửa gì, khi nào — minh bạch, hoàn tác được.
- **Duyệt hàng loạt** (`approve_many`) cho người tạo nhiều bài.
- **Đồng hồ thời gian review** (tùy chọn) — đo hiệu suất biên tập.

Trạng thái bài (`enums.PostStatus`): `DRAFT → NEEDS_REVIEW → APPROVED → SCHEDULED → PUBLISHED` (hoặc `REJECTED`/`FAILED`).

---

## 9. ĐÓNG GÓI "CHẠY ĐỘC LẬP, DỄ DÙNG"

> **Điều chỉnh sau hội đồng (Fullstack):** MVP **KHÔNG freeze bằng PyInstaller**. App là một web-server localhost + APScheduler; hai phụ thuộc **không thể đóng gói kín** là (1) **CLI AI** (Node/Rust, cần đăng nhập riêng) và (2) Chromium (chỉ khi dùng Playwright). Vì đã chọn **Graph API → bỏ Chromium**, phụ thuộc ngoài duy nhất còn lại là CLI AI — xử lý bằng **wizard onboarding**, không phải bằng code đóng gói.

### 9.1 Chiến lược đóng gói theo giai đoạn
- **MVP — Launcher 1-cú-nhấp (khuyến nghị):** file double-click (`.command` cho macOS, `.bat` cho Windows) theo mẫu `start.sh` sẵn có: kiểm tra/cài `uv` → `uv sync` → khởi tạo DB → chạy web → **tự mở trình duyệt**. Người dùng **không gõ lệnh, không thấy terminal**.
- **v2 — Installer đẹp:** `briefcase` (tạo `.app`/`.msi`) hoặc **PyInstaller onedir** cho phần Python (khai báo `datas` cho migrations Alembic + templates Jinja2 + static). **Vẫn phải** kèm bước cài + đăng nhập CLI AI riêng.
- **Dữ liệu**: SQLite + thư mục `data/` đặt trong **thư mục Home người dùng** (tránh mất khi cập nhật app).

### 9.2 Trải nghiệm khởi động
- Bấm 1 file là chạy, tự mở trình duyệt tới giao diện. (Lý tưởng v2: icon menu bar/taskbar để **Bật/Tắt/Mở giao diện**.)
- **Màn hình chẩn đoán first-run**: tự dò CLI AI (`shutil.which`) + kiểm tra kết nối Facebook → hiện **đèn xanh/đỏ + nút khắc phục** (theo góp ý UX + QA).

### 9.3 Kiến trúc chạy (kỹ thuật — chốt từ Fullstack)
- **1 process duy nhất**: `BackgroundScheduler` (APScheduler) chạy chung process với web app → tránh tranh chấp; SQLite bật `busy-timeout` (đã có trong `db.py`).
- **Sinh bài chạy background job** (mẫu `web/jobs.py`): gọi CLI AI qua `subprocess` có timeout (đã có trong `CliProviderConfig`) để **không chặn UI**; UI hiển thị tiến trình "đang viết…".
- Job store SQLAlchemy để **lịch còn nguyên sau khi tắt/mở lại app**.

### 9.4 Cảnh báo hệ điều hành (UX)
App chưa ký số → macOS **Gatekeeper** / Windows **SmartScreen** sẽ cảnh báo khi mở lần đầu. → Cần hướng dẫn "mở lần đầu" rõ ràng (macOS: chuột phải → Open; Windows: More info → Run anyway), và cân nhắc **ký số (code signing)** cho bản phát hành chính thức.

---

## 10. KẾ HOẠCH THỰC HIỆN THEO GIAI ĐOẠN

| Giai đoạn | Nội dung | Kết quả |
|---|---|---|
| **P0 — Khởi tạo** | Copy khung từ `fb-linkedin-auto`, đổi tên package `fbauto`, cắt module thừa (§3.3), đổi timezone `Asia/Ho_Chi_Minh`, chỉ giữ Facebook | App chạy được UI trống, DB khởi tạo |
| **P1 — Sinh bài không-API** | Nối `content/generator` + `llm.py` (chỉ 3 CLI + local), màn "Tạo bài", nút "Kiểm tra kết nối AI" | Nhập chủ đề → ra bài nháp |
| **P2 — Review/Sửa** | Màn duyệt + xem trước Facebook + sửa + "AI viết lại" + cổng chất lượng | Duyệt/sửa/từ chối bài |
| **P3 — Đăng Facebook** | Publisher Fanpage (Graph API) + mở rộng browser cho Fanpage; nút "Đăng thử (nháp)" | Đăng thật 1 bài lên Fanpage test |
| **P4 — Hẹn giờ** | Nối `scheduler/service`, màn Lịch (calendar), công tắc "Tạm dừng tất cả" | Bài tự đăng đúng giờ |
| **P5 — Onboarding + Hướng dẫn** | Wizard 5 bước, trang help tiếng Việt có ảnh, video ngắn, thông báo lỗi thân thiện | Người không rành IT tự setup được |
| **P6 — Đóng gói** | PyInstaller/briefcase macOS + Windows, icon, tài liệu người dùng | File cài chạy độc lập |
| **P7 — QA + Hội đồng nghiệm thu** | Chạy bộ test (§11), hội đồng review lần cuối, sửa theo góp ý | Thành phẩm bàn giao |

---

## 11. KẾ HOẠCH KIỂM THỬ (QA)

### 11.1 Chiến lược theo tầng
- **Unit (tự động):** logic thuần — chọn bài cho lịch, frequency/daily cap, chống trùng, parse giờ, cổng chất lượng, dựng lệnh CLI. *(Dự án tham khảo đã có nhiều test tương đương: `test_scheduler`, `test_publishers`, `test_llm_provider`, `test_gates`, `test_review_timer`…)*
- **Integration (tự động, có mock):** sinh bài với CLI giả (fake subprocess), đăng với publisher `dry_run`.
- **E2E thủ công (không tự động được):** đăng nhập AI thật, đăng bài thật lên **Fanpage test**, kiểm tra hẹn giờ qua đêm.

### 11.2 Test case trọng yếu (kỳ vọng)
1. Hẹn giờ đăng đúng thời điểm (theo đúng múi giờ VN).
2. Máy ngủ/tắt lúc tới giờ → tỉnh dậy đăng **đúng 1 lần** (không dồn).
3. Bài đã đăng không bị đăng lại (chống trùng qua `external_id`).
4. Vượt trần bài/ngày hoặc chưa đủ giãn cách → **hoãn**, không spam.
5. CLI AI lỗi/timeout → thông báo rõ + **fallback** provider khác; không crash.
6. Mất mạng khi đăng → bài chuyển `FAILED` + thông báo + cho **đăng lại**.
7. Session Facebook (browser) hết hạn → thông báo "Kết nối lại", không âm thầm thất bại.
8. Bài rỗng/quá dài/vi phạm giới hạn Facebook → cổng chất lượng chặn trước khi đăng.
9. Người dùng bấm "Tạm dừng tất cả lịch" → không bài nào tự đăng.
10. Chưa duyệt (mặc định) → tuyệt đối không tự đăng.

### 11.3 Trường hợp biên cần chú ý
Đổi giờ mùa (DST) & múi giờ; 2FA Facebook; Facebook đổi giao diện (làm hỏng Playwright — nên ưu tiên Graph API); token Facebook hết hạn 60 ngày (nhắc gia hạn); nhiều lịch trùng giờ.

### 11.4 Tiêu chí "đủ tốt để giao" (Exit criteria)
- Toàn bộ unit/integration test xanh; ≥1 lần E2E đăng thật + hẹn giờ qua đêm thành công trên Fanpage test.
- Người dùng thử (không rành IT) tự hoàn tất onboarding **không cần trợ giúp** trong ≤15 phút.
- Không có đường nào tự đăng khi chưa duyệt (trừ khi người dùng chủ động bật AUTO).

---

## 12. RỦI RO & GIẢM THIỂU

| Rủi ro | Mức | Giảm thiểu |
|---|---|---|
| **Khoá tài khoản Facebook** do tự động hoá (nhất là profile cá nhân/Playwright) | Cao | Ưu tiên **Fanpage + Graph API**; tần suất thấp, giờ tự nhiên; cảnh báo rõ trong app |
| **Vi phạm ToS** khi scrape web AI | Cao | **Không scrape**; chỉ dùng CLI chính hãng (Cách A) |
| Giao diện Facebook đổi → Playwright hỏng | TB | Ưu tiên Graph API; selector linh hoạt; test định kỳ |
| Token Facebook hết hạn (60 ngày) | TB | Nhắc gia hạn; hiển thị hạn dùng |
| CLI AI thay đổi cờ dòng lệnh | TB | Cấu hình lệnh nằm trong `settings.yaml` (đã tách sẵn), sửa không cần build lại |
| Người dùng không cài nổi CLI | TB | Video + nút "Hướng dẫn cài"; hoặc bản đóng gói kèm sẵn |
| Bảo mật token/PII | Cao | Lưu Keychain/`.env` cục bộ; không log token; không gửi ra ngoài |
| AI viết sai/nhảm/nhạy cảm | TB | **Bắt buộc người duyệt**; cổng chất lượng; nút "AI viết lại" |

> **Tuân thủ Block8.ai:** Không nhập credential/PII khách hàng vào tài liệu hay công cụ AI. Nếu triển khai cho khách, nêu rõ rủi ro ToS bằng văn bản và để khách chấp nhận. Vướng mắc ISMS → liên hệ đội compliance và tạo task trên ClickUp (không tự quyết).

---

## 13. HỘI ĐỒNG THẨM ĐỊNH

Hội đồng gồm 5 vai được triệu tập để phản biện plan này: **UI/UX Designer, Product Owner, Fullstack Developer, QA, End User**. Kết quả phản biện & các điều chỉnh được tổng hợp ở **§14** bên dưới.

---

## 14. TỔNG HỢP PHẢN BIỆN CỦA HỘI ĐỒNG

5 vai đã phản biện độc lập. Dưới đây là **kết luận đồng thuận**, **điểm đã sửa vào plan**, và **quyết định cần chốt**.

### 14.1 Đồng thuận nổi bật (cả hội đồng cùng hướng)
1. **Đăng Facebook: chọn Graph API (Page token) làm đường CHÍNH, Playwright chỉ là tùy chọn.**
   *(Fullstack + PO + QA đồng ý)* — an toàn tài khoản, đúng luật, auditable (phù hợp ISO 27001), và **bỏ được Chromium → đóng gói nhẹ hơn hẳn**. → Đã nâng thành khuyến nghị cứng ở §0/§7.3/§9.
2. **Sinh bài: giữ CLI subscription (Cách A), tuyệt đối không scrape web.**
   *(Fullstack + UX + End User)* — deterministic, có exit code/timeout/fallback, không bot-detection.
3. **Human-in-the-loop là bắt buộc và là điểm bán hàng.** Mặc định mọi bài phải người duyệt; không tự đăng khi chưa duyệt. *(Cả 5 vai — End User coi đây là điều kiện tiên quyết để dám dùng)*.
4. **Giấu toàn bộ tầng kỹ thuật** (CLI, localhost, token, terminal). Nếu chỉ đầu tư 1 chỗ: **onboarding + màn hình chẩn đoán tự sửa lỗi (đèn xanh/đỏ)**. *(UX + End User)*.
5. **Không được "âm thầm thất bại".** Đăng xong phải báo rõ thành công/thất bại + **link bài thật** để người dùng tự kiểm chứng. *(UX + QA + End User)*.

### 14.2 Điểm đã SỬA vào plan theo góp ý
| Góp ý | Của vai | Đã sửa ở |
|---|---|---|
| MVP không freeze bằng PyInstaller; dùng **launcher script + `uv` + wizard first-run** | Fullstack | §9 (viết lại) |
| Sinh bài phải chạy **background job**, không chặn request (mẫu `web/jobs.py`) | Fullstack | §9.3 (mới) |
| **1 process** (BackgroundScheduler chung web), SQLite `busy-timeout` | Fullstack | §9.3 (mới) |
| Lịch lỡ (máy ngủ/tắt) → **hỏi "đăng ngay / đổi giờ / huỷ"**, KHÔNG tự đăng bài lỗi thời | PO + QA | §5 + §11.2 (chính sách catch-up) |
| **Đếm ngược trước khi đăng** ("15 phút nữa sẽ đăng bài này — bấm Huỷ nếu không muốn") | End User | §6.2 |
| Trang **"Cam kết an toàn"**: an toàn với Facebook không, có tốn tiền không, dữ liệu lưu ở đâu | End User | §6.4 (mới) |
| Màn hình **Disclaimer + đồng ý rủi ro** khi cài + **rate-limit** đăng | PO | §12 + §6.3 |
| Review **2 cột** (trái: preview y hệt Facebook; phải: ô sửa + nút nhanh) + **"Quay lại bản trước"** khi AI viết lại | UX | §8 (bổ sung) |
| Idempotency theo **khóa duy nhất mỗi lịch**, dung sai **±60s**, **clock injection** để test | QA | §11 |
| Đóng gói cảnh báo Gatekeeper/SmartScreen (app chưa ký số) → hướng dẫn "mở lần đầu" | UX | §9.4 (mới) |
| Hỗ trợ **video tiếng Việt + ảnh khoanh đỏ + checklist + Zalo/điện thoại** | End User | §7 (nguyên tắc) + §6.4 |

### 14.3 Thuật ngữ → tiếng Việt đời thường (chốt từ End User + UX)
`API/token` → **"Chìa khoá kết nối"** (hoặc giấu hẳn) · `CLI/Terminal` → **không cho người dùng đụng vào** · `session` → **"Lần đăng nhập Facebook"** · `cron/schedule` → **"Hẹn giờ đăng bài"** · `prompt` → **"Chủ đề muốn viết"** · `draft` → **"Bài nháp"** · `config` → **"Cài đặt"** · `deploy/build/install` → gộp thành **1 nút "Cài đặt"**.

### 14.4 QUYẾT ĐỊNH TUÂN THỦ cần chốt trước khi code (⚠ đưa compliance team)
PO và Fullstack cùng nêu **2 điểm phải có ý kiến compliance Block8.ai trước go-live** (không tự quyết):
1. **Tính hợp lệ ToS của cơ chế "CLI subscription cho sinh bài"** — dùng CLI chính hãng đăng nhập bằng subscription để sinh nội dung tự động: cần xác nhận không vi phạm điều khoản từng nhà cung cấp (Anthropic/OpenAI/Google). *(Lưu ý: các CLI này là công cụ chính hãng, nhưng cách dùng headless/hàng loạt nên được rà soát.)*
2. **Lưu trữ Facebook Page token cục bộ** dưới góc độ dữ liệu cá nhân/ISMS (mã hoá tại máy, không đưa vào công cụ AI, không log).

→ **Hành động:** nêu 2 điểm này với **compliance team** và **tạo task trên ClickUp**. Không khoá phạm vi v1 cho tới khi có phản hồi. *(Theo quy định Block8.ai — không chặn công việc, nhưng phải raise.)*

### 14.5 "Khoảnh khắc thành công" (đề xuất UX quan trọng)
Kết thúc onboarding bằng việc **sinh + xem trước 1 bài demo ngay lập tức**, để người dùng có trải nghiệm thành công đầu tiên trước khi phải cấu hình gì thêm. *(UX)*.

---

## 15. KẾT LUẬN & BƯỚC TIẾP THEO

**Tính khả thi: RẤT cao.** Tái sử dụng ~70% code lõi từ `fb-linkedin-auto` (theo đánh giá Fullstack), MVP còn ~2.5–3k LOC. Hai quyết định kiến trúc đã chốt:
- **Sinh bài:** CLI subscription (`content/llm.py` giữ nguyên) — không API key.
- **Đăng Facebook:** Graph API Page token (`facebook_api.py`) làm chính — bỏ Chromium, gói gọn.

**Bước tiếp theo đề xuất:**
1. Bạn xác nhận **phạm vi v1** (§1) và **2 quyết định kiến trúc** ở trên.
2. Tôi raise **2 điểm tuân thủ** (§14.4) + tạo task ClickUp (khi bạn đồng ý).
3. Bắt đầu **P0 → P1** (§10): dựng khung `fbauto`, nối sinh bài, ra bài nháp đầu tiên.

> **Nhắc lại:** đây là **BẢN NHÁP NỘI BỘ**. Cần người review + ý kiến compliance trước khi triển khai cho khách hàng.
