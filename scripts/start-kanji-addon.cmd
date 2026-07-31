@echo off
setlocal

set "BUILDER_ROOT=%~dp0"
if not exist "%BUILDER_ROOT%scripts\start-kanji-addon.ps1" (
  set "BUILDER_ROOT=%~dp0..\"
)
set "BUILDER_SCRIPT=%BUILDER_ROOT%scripts\start-kanji-addon.ps1"
if not exist "%BUILDER_SCRIPT%" (
  echo The kanji builder files are incomplete.
  echo Extract the ZIP again, then run this file from the extracted folder.
  pause > nul
  exit /b 1
)

set "POWERSHELL_EXE=%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe"
if not exist "%POWERSHELL_EXE%" (
  echo Windows PowerShell 5.1 was not found.
  pause > nul
  exit /b 1
)

"%POWERSHELL_EXE%" -NoProfile -ExecutionPolicy Bypass -File "%BUILDER_SCRIPT%"
set "BUILD_EXIT_CODE=%ERRORLEVEL%"
if not "%BUILD_EXIT_CODE%"=="0" (
  echo.
  echo Could not build the kanji add-on. Check the message above.
  echo Press any key to close this window.
  pause > nul
)
exit /b %BUILD_EXIT_CODE%
