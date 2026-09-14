@echo off
rem Windows installer launcher. Keep this file ASCII-only: cmd reads it in the OEM codepage.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0windows\install.ps1"
