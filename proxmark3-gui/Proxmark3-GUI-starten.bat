@echo off
REM Zum Starten der Proxmark3-GUI unter Windows einfach doppelklicken.
REM Dieses Fenster offen lassen, solange die Oberflaeche genutzt wird.
chcp 65001 >nul
cd /d "%~dp0"

REM Python suchen: zuerst "python", dann den Python-Starter "py".
set "PY="
python --version >nul 2>nul && set "PY=python"
if not defined PY py -3 --version >nul 2>nul && set "PY=py -3"
if not defined PY goto :kein_python

echo Starte Proxmark3-GUI ...
%PY% start.py %*
echo.
echo Die Oberflaeche wurde beendet.
pause
exit /b 0

:kein_python
echo Python 3 wurde nicht gefunden.
echo Bitte von https://www.python.org/downloads/ installieren und beim Setup
echo unbedingt "Add Python to PATH" anhaken. Danach diese Datei erneut starten.
pause
exit /b 1
