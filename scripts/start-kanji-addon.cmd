@echo off
chcp 65001 > nul
set "BUILDER_ROOT=%~dp0"
if not exist "%BUILDER_ROOT%scripts\start-kanji-addon.ps1" (
  set "BUILDER_ROOT=%~dp0..\"
)

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%BUILDER_ROOT%scripts\start-kanji-addon.ps1"
if errorlevel 1 (
  echo.
  echo 한자 확장을 만들지 못했습니다. 위 안내를 확인해 주세요.
  echo 창을 닫으려면 아무 키나 누르세요.
  pause > nul
)
