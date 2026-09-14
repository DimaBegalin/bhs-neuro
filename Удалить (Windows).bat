@echo off
rem Windows uninstaller launcher. Keep this file ASCII-only: cmd reads it in the OEM codepage.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0windows\uninstall.ps1"
