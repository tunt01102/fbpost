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

echo "==> Mở giao diện tại http://localhost:8000 ..."
uv run fbauto serve
