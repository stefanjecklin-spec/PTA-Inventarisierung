@echo off
setlocal EnableExtensions
chcp 65001 >nul 2>&1
title PTA Inventarisierung - Verknuepfungen anlegen
cd /d "%~dp0"

set "ZIEL=%~dp0dist\PTA-Inventarisierung.exe"
if not exist "%ZIEL%" set "ZIEL=%~dp0PTA-Inventarisierung.exe"
if not exist "%ZIEL%" (
    echo.
    echo   PTA-Inventarisierung.exe wurde nicht gefunden.
    echo   Bitte zuerst build.bat ausfuehren oder die Datei hierher kopieren.
    echo.
    pause
    exit /b 1
)

echo.
echo   Verknuepfungen werden angelegt fuer:
echo     %ZIEL%
echo.

powershell -NoProfile -Command ^
  "$w = New-Object -ComObject WScript.Shell;" ^
  "foreach ($ort in @([Environment]::GetFolderPath('Desktop'), (Join-Path $env:APPDATA 'Microsoft\Windows\Start Menu\Programs'))) {" ^
  "  $v = $w.CreateShortcut((Join-Path $ort 'PTA Inventarisierung.lnk'));" ^
  "  $v.TargetPath = '%ZIEL%';" ^
  "  $v.WorkingDirectory = Split-Path '%ZIEL%';" ^
  "  $v.IconLocation = '%ZIEL%,0';" ^
  "  $v.Description = 'Pruef- und Abschlusskontrolle FTTH';" ^
  "  $v.Save();" ^
  "  Write-Host ('   angelegt: ' + $ort) }"

echo.
echo   Fertig. Das Programm laesst sich jetzt ueber das Startmenue und
echo   ueber das Symbol auf dem Desktop starten.
echo.
pause
