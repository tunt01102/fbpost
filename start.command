#!/bin/bash
# Launcher 1-cú-nhấp cho macOS: double-click file này để chạy app.
# Tự cài phụ thuộc bằng uv, khởi tạo DB, chạy web, mở trình duyệt.
set -e
cd "$(dirname "$0")"

echo "==> FB Auto Poster đang khởi động..."

if ! command -v uv >/dev/null 2>&1; then
  echo "==> Đang cài 'uv' (trình quản lý gói Python)..."
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.local/bin:$PATH"
fi

echo "==> Cài đặt phụ thuộc..."
uv sync

echo "==> Khởi tạo cơ sở dữ liệu..."
uv run fbauto init-db

echo "==> Kiểm tra Google Antigravity CLI..."
export PATH="$HOME/.local/bin:$HOME/bin:$HOME/.antigravity/bin:$PATH"
if ! command -v agy >/dev/null 2>&1; then
  echo "==> Chưa có 'agy' — đang cài Antigravity CLI chính thức từ antigravity.google..."
  if curl -fsSL https://antigravity.google/cli/install.sh | bash; then
    export PATH="$HOME/.local/bin:$HOME/bin:$HOME/.antigravity/bin:$PATH"
  else
    echo "⚠ Không cài được Antigravity CLI. App vẫn mở; xem hướng dẫn trong Cài đặt."
  fi
fi

if command -v agy >/dev/null 2>&1; then
  if [ ! -f "data/.antigravity_setup_complete" ]; then
    echo "==> Đăng nhập Google AI Ultra lần đầu..."
    echo "    Trình duyệt có thể tự mở. Hãy chọn đúng tài khoản có gói AI Ultra."
    if ! uv run fbauto setup-antigravity; then
      echo "⚠ Chưa đăng nhập xong. Bạn có thể đăng nhập lại trong trang Cài đặt."
    fi
  else
    echo "==> Antigravity đã được thiết lập."
  fi
else
  echo "⚠ Không tìm thấy lệnh 'agy' sau khi cài. Hãy mở lại Terminal hoặc dùng trang Cài đặt."
fi

echo "==> Mở giao diện tại http://localhost:8791 ..."
uv run fbauto serve
