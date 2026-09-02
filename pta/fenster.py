"""Das Programmfenster.

Es gibt drei Wege, die Oberflaeche zu zeigen, in dieser Reihenfolge versucht:

1. Anwendungsfenster von Edge oder Chrome (``--app=``). Sieht aus wie ein
   eigenes Programm, hat kein Adressfeld, eigenes Symbol in der Taskleiste,
   und alle Browserfaehigkeiten bleiben erhalten — vor allem das Hineinziehen
   von Dateien aus dem Explorer.
2. Ein echtes Fenster ueber pywebview, falls installiert und mit --fenster
   verlangt. Ganz ohne Browserprozess, dafuer je nach System eingeschraenkt
   beim Hineinziehen von Dateien.
3. Der normale Browser als letzte Rueckfallebene.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import webbrowser
from pathlib import Path

FENSTERGROESSE = (1420, 920)


# --------------------------------------------------------------------------
# Meldung, wenn es kein Konsolenfenster gibt
# --------------------------------------------------------------------------
def meldung(titel: str, text: str) -> None:
    """Zeigt einen Hinweis, auch wenn das Programm ohne Konsole laeuft."""
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.user32.MessageBoxW(0, text, titel, 0x40)
            return
        except Exception:
            pass
    print(f"{titel}: {text}")


# --------------------------------------------------------------------------
# Anwendungsfenster von Edge oder Chrome
# --------------------------------------------------------------------------
# Reihenfolge der Vorliebe. Wichtig: erst alle Ordner nach Edge absuchen,
# dann nach Chrome. Sonst gewinnt Chrome aus »Programme«, weil Edge meist
# in »Programme (x86)« liegt.
BROWSER_VORLIEBE = (
    ("Microsoft Edge", "Microsoft/Edge/Application/msedge.exe",
     ("microsoft-edge", "microsoft-edge-stable", "msedge"),
     "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge"),
    ("Google Chrome", "Google/Chrome/Application/chrome.exe",
     ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser"),
     "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
    ("Brave", "BraveSoftware/Brave-Browser/Application/brave.exe",
     ("brave-browser", "brave"),
     "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser"),
)

WINDOWS_ORDNER = ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA")


def _browser_suchen(bevorzugt: str | None = None) -> tuple[str, str] | None:
    """Sucht einen Browser für das Anwendungsfenster.

    Gibt (Name, Pfad) zurück. Mit bevorzugt ("edge", "chrome", "brave") lässt
    sich ein bestimmter erzwingen.
    """
    eintraege = list(BROWSER_VORLIEBE)
    if bevorzugt:
        schluessel = bevorzugt.strip().lower()
        eintraege.sort(key=lambda e: schluessel not in e[0].lower())

    for name, windows_pfad, befehle, mac_pfad in eintraege:
        if sys.platform == "win32":
            for umgebung in WINDOWS_ORDNER:
                wurzel = os.environ.get(umgebung)
                if wurzel and (Path(wurzel) / windows_pfad).exists():
                    return name, str(Path(wurzel) / windows_pfad)
        elif sys.platform == "darwin" and Path(mac_pfad).exists():
            return name, mac_pfad
        for befehl in befehle:
            gefunden = shutil.which(befehl)
            if gefunden:
                return name, gefunden
    return None


def anwendungsfenster(adresse: str, profilordner: Path | None = None,
                      bevorzugt: str | None = None) -> bool:
    """Oeffnet ein Fenster ohne Adressfeld. Gibt True zurueck, wenn es geklappt hat."""
    gefunden = _browser_suchen(bevorzugt)
    if not gefunden:
        return False
    name, programm = gefunden
    print(f"  Fenster über: {name}")
    breite, hoehe = FENSTERGROESSE
    befehl = [programm, f"--app={adresse}", f"--window-size={breite},{hoehe}",
              "--no-first-run", "--no-default-browser-check"]
    if profilordner:
        # eigenes Profil: das Fenster ist vom normalen Browser unabhaengig und
        # laesst sich schliessen, ohne andere Fenster mitzureissen
        befehl.append(f"--user-data-dir={profilordner}")
    try:
        kein_fenster = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        subprocess.Popen(befehl, creationflags=kein_fenster) if kein_fenster \
            else subprocess.Popen(befehl)
        return True
    except Exception:
        return False


# --------------------------------------------------------------------------
# Echtes Fenster ueber pywebview
# --------------------------------------------------------------------------
def natives_fenster(adresse: str, titel: str = "PTA Inventarisierung") -> bool:
    """Blockiert, bis das Fenster geschlossen wird. False, wenn nicht moeglich."""
    try:
        import webview
    except Exception:
        return False
    breite, hoehe = FENSTERGROESSE
    try:
        webview.create_window(titel, adresse, width=breite, height=hoehe,
                              min_size=(940, 620))
        webview.start()
        return True
    except Exception:
        return False


# --------------------------------------------------------------------------
# Rueckfallebene
# --------------------------------------------------------------------------
def normaler_browser(adresse: str) -> bool:
    try:
        return bool(webbrowser.open(adresse))
    except Exception:
        return False
