@echo off
REM Launcher 1-cu-nhap cho Windows: double-click file nay de chay app.
cd /d "%~dp0"

echo ==^> FB Auto Poster dang khoi dong...

where uv >nul 2>nul
if errorlevel 1 (
  echo ==^> Dang cai 'uv' ...
  powershell -ExecutionPolicy Bypass -c "irm https://astral.sh/uv/install.ps1 | iex"
  set "PATH=%USERPROFILE%\.local\bin;%PATH%"
)

echo ==^> Cai dat phu thuoc...
uv sync

echo ==^> Khoi tao co so du lieu...
uv run fbauto init-db

echo ==^> Kiem tra Google Antigravity CLI...
where agy >nul 2>nul
if errorlevel 1 (
  echo ==^> Chua co "agy" - dang cai Antigravity CLI chinh thuc tu antigravity.google...
  powershell -NoProfile -ExecutionPolicy Bypass -Command "irm https://antigravity.google/cli/install.ps1 | iex"

  REM Nap lai PATH cua User + Machine vao cua so CMD hien tai sau khi installer cap nhat PATH.
  for /f "usebackq delims=" %%P in (`powershell -NoProfile -Command "[Environment]::GetEnvironmentVariable('Path','User') + ';' + [Environment]::GetEnvironmentVariable('Path','Machine')"`) do set "PATH=%%P"
)

where agy >nul 2>nul
if errorlevel 1 (
  echo [CANH BAO] Khong tim thay "agy" sau khi cai. App van mo; xem trang Cai dat.
) else (
  if not exist "data\.antigravity_setup_complete" (
    echo ==^> Dang nhap Google AI Ultra lan dau...
    echo     Trinh duyet co the tu mo. Hay chon dung tai khoan co goi AI Ultra.
    uv run fbauto setup-antigravity
    if errorlevel 1 (
      echo [CANH BAO] Chua dang nhap xong. Ban co the dang nhap lai trong trang Cai dat.
    )
  ) else (
    echo ==^> Antigravity da duoc thiet lap.
  )
)

echo ==^> Mo giao dien tai http://localhost:8791 ...
uv run fbauto serve
pause
