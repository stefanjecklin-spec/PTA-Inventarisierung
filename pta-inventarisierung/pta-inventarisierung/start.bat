@echo off
setlocal EnableExtensions
chcp 65001 >nul 2>&1
title PTA Inventarisierung
cd /d "%~dp0"

rem ------------------------------------------------------------------
rem  Python suchen.
rem  Zuerst der Launcher "py" - ihn faengt der Microsoft-Store-Platzhalter
rem  nie ab. Erst danach "python".
rem ------------------------------------------------------------------
set "PY="

py -3 -c "import sys" >nul 2>&1
if not errorlevel 1 set "PY=py -3"

if not defined PY (
    python -c "import sys" >nul 2>&1
    if not errorlevel 1 set "PY=python"
)

if not defined PY goto :kein_python

rem ------------------------------------------------------------------
rem  Umgebung einrichten, falls noch nicht vorhanden
rem ------------------------------------------------------------------
if not exist ".venv\Scripts\python.exe" (
    echo.
    echo   Umgebung wird eingerichtet, das dauert einmalig eine Minute ...
    echo.
    %PY% -m venv .venv
    if errorlevel 1 goto :fehler_venv
    ".venv\Scripts\python.exe" -m pip install --upgrade pip --quiet
    ".venv\Scripts\python.exe" -m pip install -r requirements.txt --quiet
    if errorlevel 1 goto :fehler_pakete
    echo   Fertig eingerichtet.
    echo.
)

rem ------------------------------------------------------------------
rem  Programm starten
rem ------------------------------------------------------------------
".venv\Scripts\python.exe" -m pta %*
goto :ende


:kein_python
echo.
echo ==================================================================
echo   Python wurde nicht gefunden.
echo ==================================================================
echo.
echo   Die Meldung vom Microsoft Store bedeutet: Windows hat nur einen
echo   Platzhalter statt eines echten Python gefunden.
echo.
echo   So geht es weiter:
echo.
echo     1. https://www.python.org/downloads/windows/ oeffnen
echo     2. "Windows installer (64-bit)" herunterladen
echo     3. Beim Installieren unten "Add python.exe to PATH" ankreuzen
echo     4. Dieses Fenster schliessen und start.bat erneut starten
echo.
echo   Pruefen laesst sich das danach mit:  py --version
echo.
pause
exit /b 1

:fehler_venv
echo.
echo   Die Umgebung konnte nicht angelegt werden.
echo   Moeglicher Grund: fehlende Schreibrechte in diesem Ordner.
echo   Verschiebe den Ordner nach C:\PTA und versuche es nochmals.
echo.
pause
exit /b 1

:fehler_pakete
echo.
echo   Die benoetigten Pakete konnten nicht geladen werden.
echo   Moeglicher Grund: keine Internetverbindung oder eine Firewall,
echo   die pypi.org blockiert. Das ist nur beim ersten Start noetig,
echo   danach laeuft das Programm ohne Internet.
echo.
pause
exit /b 1

:ende
endlocal
