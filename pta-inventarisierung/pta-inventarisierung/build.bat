@echo off
setlocal EnableExtensions
chcp 65001 >nul 2>&1
title PTA Inventarisierung - Programmdatei bauen
cd /d "%~dp0"

echo.
echo ==================================================================
echo   Programmdatei PTA-Inventarisierung.exe wird gebaut
echo   Das dauert beim ersten Mal einige Minuten.
echo ==================================================================
echo.

rem --- Python suchen ---
set "PY="
py -3 -c "import sys" >nul 2>&1
if not errorlevel 1 set "PY=py -3"
if not defined PY (
    python -c "import sys" >nul 2>&1
    if not errorlevel 1 set "PY=python"
)
if not defined PY (
    echo   Python wurde nicht gefunden. Bitte zuerst start.bat ausfuehren.
    pause
    exit /b 1
)

rem --- Umgebung vorbereiten ---
if not exist ".venv\Scripts\python.exe" (
    echo   Umgebung wird eingerichtet ...
    %PY% -m venv .venv
    if errorlevel 1 goto :fehler
)
set "VPY=.venv\Scripts\python.exe"

echo   Bibliotheken werden geladen ...
"%VPY%" -m pip install --upgrade pip --quiet
"%VPY%" -m pip install -r requirements.txt pyinstaller --quiet
if errorlevel 1 goto :fehler

rem --- pywebview ist freiwillig: damit gibt es ein eigenes Programmfenster ---
echo   Optionales Programmfenster wird eingerichtet ...
"%VPY%" -m pip install pywebview --quiet

echo.
echo   Programmdatei wird erzeugt ...
echo.
"%VPY%" -m PyInstaller --noconfirm --clean --onefile ^
    --name PTA-Inventarisierung ^
    --add-data "pta/static;static" ^
    --collect-submodules pypdf ^
    --collect-all pypdfium2 ^
    --collect-submodules PIL ^
    --hidden-import waitress ^
    --icon pta/static/icon.ico ^
    --windowed ^
    run.py
if errorlevel 1 goto :fehler

echo.
echo ==================================================================
echo   Fertig.
echo.
echo   Die Datei liegt hier:
echo     %cd%\dist\PTA-Inventarisierung.exe
echo.
echo   Sie laeuft auf jedem Windows-Rechner ohne Installation und
echo   oeffnet ein eigenes Programmfenster ohne Browserrahmen.
echo   Am besten in einen eigenen Ordner kopieren, zum Beispiel C:\PTA -
echo   daneben legt sie beim Start den Ordner "daten" an.
echo ==================================================================
echo.
pause
goto :ende

:fehler
echo.
echo   Der Bau ist fehlgeschlagen. Die Meldungen darueber sagen, woran es lag.
echo.
pause
exit /b 1

:ende
endlocal
