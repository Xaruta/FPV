@echo off
rem Stoppt FPV-Lagezentrum Web (Port 8767).
for /f "tokens=5" %%p in (%SystemRoot%\System32\netstat.exe -ano ^| findstr /r /c:"127.0.0.1:8767 .*LISTENING") do taskkill /pid %%p /f >nul 2>&1
echo FPV-Lagezentrum Web gestoppt.
