@echo off
chcp 65001 >nul
setlocal

cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\restart.ps1" %*

if errorlevel 1 (
    echo.
    echo 重启失败，请查看上方错误信息。
    pause
    exit /b 1
)

exit /b 0
