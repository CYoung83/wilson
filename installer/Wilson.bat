@echo off
title Wilson -- AI Reasoning Auditor
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Wilson_launcher.ps1"
