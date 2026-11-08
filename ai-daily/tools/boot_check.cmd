@echo off
rem SessionStart hook entry for the AI daily check.
rem NOTE: keep this file ASCII-only. cmd.exe parses .cmd as the OEM code page,
rem so any non-ASCII byte (even inside rem comments) can break the script.
rem It only locates python, runs boot_check.py, and passes its JSON stdout through.
rem
rem Do not pin one bundled version here: WorkBuddy upgrades move that directory.
rem Prefer whatever "python" resolves to, then fall back to a bundled interpreter.
setlocal

set "PY="
where python >nul 2>&1
if not errorlevel 1 set "PY=python"

if not defined PY (
  for /d %%D in ("%USERPROFILE%\.workbuddy\binaries\python\versions\*") do (
    if exist "%%D\python.exe" set "PY=%%D\python.exe"
  )
)

if not defined PY exit /b 0

"%PY%" "%~dp0boot_check.py"
exit /b 0
