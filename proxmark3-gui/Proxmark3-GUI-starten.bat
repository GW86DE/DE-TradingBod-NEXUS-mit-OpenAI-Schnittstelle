@echo off
REM Zum Starten der Proxmark3-GUI unter Windows einfach doppelklicken.
cd /d "%~dp0"

where python >nul 2>nul
if %errorlevel%==0 (
  set PY=python
) else (
  where py >nul 2>nul
  if %errorlevel%==0 (
    set PY=py
  ) else (
    echo Python 3 wurde nicht gefunden. Bitte von python.org installieren
    echo und beim Setup "Add Python to PATH" anhaken.
    pause
    exit /b 1
  )
)

echo Starte Proxmark3-GUI ...
%PY% start.py %*
pause
