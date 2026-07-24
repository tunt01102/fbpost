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

echo ==^> Mo giao dien tai http://localhost:8000 ...
uv run fbauto serve
pause
