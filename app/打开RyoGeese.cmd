@echo off
chcp 65001 >nul
powershell.exe -NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File "%~dp0启动软件.ps1"
