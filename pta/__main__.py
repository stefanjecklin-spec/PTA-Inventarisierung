"""Startpunkt des Programms.

Ohne Zusatz oeffnet sich ein eigenes Programmfenster ohne Adressfeld.
Wird es geschlossen, beendet sich das Programm von selbst.

    python -m pta                    Programmfenster
    python -m pta --browser          im normalen Browser
    python -m pta --fenster          echtes Fenster ueber pywebview
    python -m pta --daten D:\\PTA     eigener Datenordner
"""

from __future__ import annotations

import argparse
import json
import os
import socket
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

from . import fenster
from .ablage import Ablage, standard_datenordner
from .server import erzeuge_app

VERSION = "1.13.0"
STANDARDPORT = 8731
STILLE_BIS_ENDE = 180        # Sekunden ohne Lebenszeichen, dann Programmende


# --------------------------------------------------------------------------
# Hilfsmittel
# --------------------------------------------------------------------------
def port_frei(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("127.0.0.1", port)) != 0


def freier_port(bevorzugt: int = STANDARDPORT) -> int:
    for port in range(bevorzugt, bevorzugt + 40):
        if port_frei(port):
            return port
    return 0


def laeuft_schon(port: int) -> bool:
    """Prueft, ob auf dem Port bereits dieses Programm antwortet."""
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/version", timeout=1.5) as a:
            return json.loads(a.read()).get("programm") == "PTA Inventarisierung"
    except (urllib.error.URLError, OSError, ValueError):
        return False


def dienst_starten(app, port: int) -> None:
    try:
        from waitress import serve
        serve(app, host="127.0.0.1", port=port, threads=6, ident=None)
    except ImportError:
        app.run(host="127.0.0.1", port=port, debug=False)


def warten_bis_bereit(port: int, sekunden: float = 12.0) -> bool:
    ende = time.time() + sekunden
    while time.time() < ende:
        if not port_frei(port):
            return True
        time.sleep(0.12)
    return False


def wachhund(app, stille: int = STILLE_BIS_ENDE) -> None:
    """Beendet das Programm, wenn sich die Oberflaeche nicht mehr meldet."""
    while True:
        time.sleep(15)
        if time.time() - app.letzter_kontakt > stille:
            os._exit(0)


def protokoll_umleiten(ablage: Ablage) -> None:
    """Ohne Konsolenfenster muessen Meldungen in eine Datei."""
    if sys.stdout is not None and sys.stdout.isatty():
        return
    try:
        datei = open(ablage.ordner / "programm.log", "a", encoding="utf-8", buffering=1)
        datei.write(f"\n--- Start {time.strftime('%Y-%m-%d %H:%M:%S')} ---\n")
        sys.stdout = sys.stderr = datei
    except Exception:
        pass


# --------------------------------------------------------------------------
# Hauptablauf
# --------------------------------------------------------------------------
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="pta", description="PTA Inventarisierung — Prüf- und Abschlusskontrolle FTTH")
    parser.add_argument("--daten", type=Path, default=None,
                        help="Datenordner (Vorgabe: ./daten neben dem Programm)")
    parser.add_argument("--port", type=int, default=None, help="fester Port")
    parser.add_argument("--browser", action="store_true",
                        help="im normalen Browser öffnen statt im Programmfenster")
    parser.add_argument("--fenster", action="store_true",
                        help="echtes Fenster über pywebview, ganz ohne Browserprozess")
    parser.add_argument("--kein-fenster", action="store_true",
                        help="nur den Dienst starten, nichts öffnen")
    parser.add_argument("--kein-autostop", action="store_true",
                        help="weiterlaufen, auch wenn das Fenster geschlossen wird")
    parser.add_argument("--version", action="version", version=f"PTA Inventarisierung {VERSION}")
    args = parser.parse_args(argv)

    ablage = Ablage(args.daten or standard_datenordner())
    protokoll_umleiten(ablage)
    einstellungen = ablage.einstellungen_laden()

    # Befehlszeile schlägt die gespeicherte Einstellung
    ansicht = einstellungen.get("ansicht", "app")
    if args.browser:
        ansicht = "browser"
    elif args.fenster:
        ansicht = "fenster"
    if args.kein_fenster:
        ansicht = "keine"
    bevorzugter_browser = einstellungen.get("browser") or None

    # Läuft das Programm schon? Dann nur ein weiteres Fenster öffnen.
    port = args.port or STANDARDPORT
    if not args.port and not port_frei(port) and laeuft_schon(port):
        adresse = f"http://127.0.0.1:{port}/"
        if ansicht != "keine":
            fenster.anwendungsfenster(adresse, ablage.ordner / "fenster",
                                      bevorzugter_browser) \
                or fenster.normaler_browser(adresse)
        return 0

    if not args.port:
        port = freier_port()
    adresse = f"http://127.0.0.1:{port}/"
    app = erzeuge_app(ablage)

    print("=" * 62)
    print(f"  PTA Inventarisierung {VERSION}")
    print(f"  Adresse:     {adresse}")
    print(f"  Datenordner: {ablage.ordner}")
    print("=" * 62)

    # pywebview blockiert selbst, darum Dienst im Hintergrund
    if ansicht == "fenster":
        threading.Thread(target=dienst_starten, args=(app, port), daemon=True).start()
        warten_bis_bereit(port)
        if fenster.natives_fenster(adresse):
            return 0                              # Fenster wurde geschlossen
        print("  pywebview nicht verfügbar, weiter mit Programmfenster.")

    threading.Thread(target=dienst_starten, args=(app, port), daemon=True).start()
    if not warten_bis_bereit(port):
        fenster.meldung("PTA Inventarisierung",
                        "Der lokale Dienst konnte nicht gestartet werden.\n\n"
                        f"Einzelheiten stehen in:\n{ablage.ordner / 'programm.log'}")
        return 1

    if ansicht != "keine":
        geoeffnet = False
        if ansicht != "browser":
            geoeffnet = fenster.anwendungsfenster(adresse, ablage.ordner / "fenster",
                                                  bevorzugter_browser)
        if not geoeffnet:
            geoeffnet = fenster.normaler_browser(adresse)
        if not geoeffnet:
            fenster.meldung("PTA Inventarisierung",
                            "Es liess sich kein Fenster öffnen.\n\n"
                            f"Bitte diese Adresse von Hand im Browser öffnen:\n{adresse}")

    if args.kein_autostop or ansicht == "keine":
        try:
            while True:
                time.sleep(3600)
        except KeyboardInterrupt:
            return 0

    wachhund(app)
    return 0


if __name__ == "__main__":
    sys.exit(main())
