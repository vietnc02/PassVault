@echo off
cd /d "%~dp0.."
".venv\Scripts\python.exe" -m passvault.native_host %*
