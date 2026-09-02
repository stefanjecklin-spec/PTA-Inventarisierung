"""Lokaler Webserver. Bindet ausschliesslich an 127.0.0.1 — nichts geht ins Netz."""

from __future__ import annotations

import json
import os
import platform
import re
import time
import subprocess
import sys
from pathlib import Path

from flask import Flask, Response, jsonify, request, send_from_directory

from . import aktualisierung, bildvergleich, dokumente, komponenten
from .ablage import Ablage

MAX_UPLOAD = 200 * 1024 * 1024      # 200 MB je Datei
VERSION = "1.13.0"


def statischer_ordner() -> Path:
    if getattr(sys, "frozen", False):            # von PyInstaller entpackt
        return Path(getattr(sys, "_MEIPASS")) / "static"
    return Path(__file__).parent / "static"


def _pywebview_da() -> bool:
    try:
        import webview  # noqa: F401
        return True
    except Exception:
        return False


def erzeuge_app(ablage: Ablage | None = None) -> Flask:
    ablage = ablage or Ablage()
    app = Flask(__name__, static_folder=None)
    app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD
    app.ablage = ablage                          # für Tests erreichbar
    app.letzter_kontakt = time.time()            # für den Wachhund

    @app.before_request
    def _kontakt_merken():
        app.letzter_kontakt = time.time()

    statisch = statischer_ordner()

    # ---------------- Oberfläche ----------------
    @app.get("/")
    def start():
        """Liefert die Oberfläche und setzt die eigene Fassung ein.

        Ein älteres Programm ersetzt den Platzhalter nicht — daran erkennt die
        Oberfläche, dass die Programmdateien nicht zu ihr passen.
        """
        seite = (statisch / "index.html").read_text(encoding="utf-8")
        return Response(seite.replace("__FASSUNG__", VERSION), mimetype="text/html")

    @app.get("/<path:datei>")
    def datei_ausliefern(datei: str):
        return send_from_directory(statisch, datei)

    # ---------------- Zustand ----------------
    @app.get("/api/zustand")
    def zustand_lesen():
        daten = ablage.laden()
        daten["_ablage"] = {
            "ordner": str(ablage.ordner),
            "sicherungen": len(list(ablage.sicherungen.glob("zustand_*.json"))),
        }
        return jsonify(daten)

    @app.put("/api/zustand")
    def zustand_schreiben():
        daten = request.get_json(force=True, silent=True)
        if not isinstance(daten, dict) or "projects" not in daten:
            return jsonify({"fehler": "Ungültiger Zustand"}), 400
        daten.pop("_ablage", None)
        ablage.speichern(daten)
        return jsonify({"ok": True})

    # ---------------- Dokumente ----------------
    @app.post("/api/dokument")
    def dokument_pruefen():
        datei = request.files.get("datei")
        if datei is None or not datei.filename:
            return jsonify({"fehler": "Es kam keine Datei an. Wurde sie vielleicht "
                                      "während des Hineinziehens verschoben?"}), 400

        art = request.form.get("art", "original")            # original | pruefung
        projekt = request.form.get("projekt", "projekt")
        dokument = request.form.get("dokument", "dokument")
        kopie = request.form.get("kopie", "1") == "1"

        try:
            rohdaten = datei.read()
        except Exception as fehler:
            return jsonify({"fehler": f"Die Datei liess sich nicht lesen: {fehler}"}), 400

        if not rohdaten:
            return jsonify({"fehler": "Die Datei ist leer (0 Byte)."}), 400

        try:
            datensatz = dokumente.auswerten(datei.filename, rohdaten)
        except Exception as fehler:
            app.logger.exception("Auswertung fehlgeschlagen")
            return jsonify({"fehler": "Die Datei konnte nicht ausgewertet werden "
                                      f"({fehler.__class__.__name__}: {fehler})."}), 500

        text = datensatz.pop("_text", None)
        ablage.text_schreiben(datensatz["hash"], text)

        if kopie:
            try:
                datensatz["pfad"] = ablage.dokument_ablegen(
                    projekt, dokument, art, datei.filename, rohdaten)
            except Exception:
                datensatz["pfad"] = None

        antwort = {"datensatz": datensatz}

        if art == "pruefung":
            try:
                referenz = request.form.get("referenz_hash")
                ref_seiten = request.form.get("referenz_seiten")
                referenz_satz = {
                    "hash": referenz,
                    "size": int(request.form.get("referenz_groesse") or 0),
                    "pages": int(ref_seiten) if ref_seiten not in (None, "", "null") else None,
                }
                antwort["vergleich"] = dokumente.vergleichen(
                    referenz_satz, ablage.text_lesen(referenz), datensatz, text)
            except Exception as fehler:
                app.logger.exception("Vergleich fehlgeschlagen")
                return jsonify({"fehler": "Der Vergleich mit dem Original schlug fehl "
                                          f"({fehler.__class__.__name__}: {fehler})."}), 500

            # Plaene ohne Textebene seitenweise als Bild vergleichen
            if not antwort["vergleich"]["same"] and rohdaten[:5] == b"%PDF-":
                ref_pfad = request.form.get("referenz_pfad") or ""
                if ref_pfad and ablage.ist_im_datenordner(ref_pfad):
                    try:
                        antwort["vergleich"]["bilder"] = bildvergleich.vergleichen(
                            ref_pfad, rohdaten, ablage.vergleiche)
                    except Exception as fehler:
                        app.logger.exception("Bildvergleich fehlgeschlagen")
                        antwort["vergleich"]["bilder"] = {
                            "moeglich": False,
                            "grund": f"{fehler.__class__.__name__}: {fehler}"}

        return jsonify(antwort)

    @app.get("/api/vergleichsbild/<name>")
    def vergleichsbild(name: str):
        if not re.fullmatch(r"[0-9a-f]{6,32}_s\d{1,4}(x\d{1,3})?\.png", name):
            return jsonify({"fehler": "Ungültiger Bildname"}), 400
        return send_from_directory(ablage.vergleiche, name, max_age=3600)

    @app.errorhandler(413)
    def zu_gross(_fehler):
        grenze = MAX_UPLOAD // (1024 * 1024)
        return jsonify({"fehler": f"Die Datei ist grösser als {grenze} MB."}), 413

    @app.errorhandler(500)
    def unerwartet(fehler):
        return jsonify({"fehler": f"Unerwarteter Fehler im Programm: {fehler}"}), 500

    @app.get("/api/selbsttest")
    def selbsttest():
        ergebnis = ablage.selbsttest()
        ergebnis["bildvergleich"] = bildvergleich.verfuegbar()
        if not ergebnis["bildvergleich"]:
            ergebnis["probleme"].append(
                "pypdfium2 oder Pillow fehlt — Pläne ohne Textebene werden nur am "
                "Fingerabdruck verglichen, ohne Markierung der geänderten Stellen.")
            ergebnis["ok"] = False
        return jsonify(ergebnis)

    # ---------------- Ordner öffnen ----------------
    @app.post("/api/ordner")
    def ordner_oeffnen():
        wunsch = (request.get_json(silent=True) or {})
        ziel = Path(wunsch.get("pfad") or ablage.ordner)
        if not ziel.exists():
            ziel = ablage.ordner
        if ziel.is_file():
            ziel = ziel.parent
        try:
            system = platform.system()
            if system == "Windows":
                os.startfile(ziel)                        # noqa: S606
            elif system == "Darwin":
                subprocess.Popen(["open", str(ziel)])
            else:
                subprocess.Popen(["xdg-open", str(ziel)])
            return jsonify({"ok": True, "pfad": str(ziel)})
        except Exception as fehler:
            return jsonify({"ok": False, "fehler": str(fehler)}), 500

    @app.post("/api/aufraeumen")
    def aufraeumen():
        entfernt = ablage.aufraeumen(ablage.laden())
        return jsonify({"ok": True, "entfernt": entfernt})

    @app.get("/api/einstellungen")
    def einstellungen_lesen():
        werte = ablage.einstellungen_laden()
        werte["fenster_moeglich"] = _pywebview_da()
        return jsonify(werte)

    @app.put("/api/einstellungen")
    def einstellungen_schreiben():
        werte = request.get_json(silent=True) or {}
        return jsonify(ablage.einstellungen_speichern(werte))

    @app.post("/api/komponenten")
    def komponenten_lesen():
        """Liest eine Komponentenliste aus dem PTA-AM.

        Wird eine frühere Ausgabe mitgeschickt, kommt zusätzlich der Vergleich:
        was ist erledigt, was steht weiterhin offen, was kam dazu.
        """
        datei = request.files.get("datei")
        if datei is None or not datei.filename:
            return jsonify({"fehler": "Es kam keine Datei an."}), 400
        rohdaten = datei.read()
        if not rohdaten:
            return jsonify({"fehler": "Die Datei ist leer (0 Byte)."}), 400

        try:
            daten = komponenten.lesen(rohdaten)
        except ValueError as fehler:
            return jsonify({"fehler": str(fehler)}), 400
        except Exception as fehler:
            app.logger.exception("Komponentenliste fehlgeschlagen")
            return jsonify({"fehler": "Die Liste konnte nicht gelesen werden "
                                      f"({fehler.__class__.__name__})."}), 500

        daten["datei"] = datei.filename
        try:
            daten["pfad"] = ablage.dokument_ablegen(
                request.form.get("projekt", "projekt"), "Komponentenliste",
                "pta-am", datei.filename, rohdaten)
        except Exception:
            daten["pfad"] = None

        antwort = {"liste": daten}
        vorher = request.form.get("vorher")
        if vorher:
            try:
                antwort["vergleich"] = komponenten.vergleichen(json.loads(vorher), daten)
            except Exception:
                antwort["vergleich"] = None
        return jsonify(antwort)

    @app.get("/api/update")
    def update_nachsehen():
        """Sieht nach, ob auf GitHub eine neuere Fassung bereitliegt.

        Hoechstens einmal pro Tag, ausser mit ?jetzt=1. Ohne Internet oder ohne
        hinterlegtes Verzeichnis wird das schlicht gemeldet.
        """
        from datetime import date
        werte = ablage.einstellungen_laden()
        erzwingen = request.args.get("jetzt") == "1"

        if not werte.get("update_pruefen") and not erzwingen:
            return jsonify({"ok": False, "grund": "Die Prüfung ist ausgeschaltet.",
                            "aus": True})

        zwischenstand = werte.get("update_stand") or {}
        if not erzwingen and zwischenstand.get("geprueft") == date.today().isoformat():
            zwischenstand["aus_zwischenspeicher"] = True
            return jsonify(zwischenstand)

        ergebnis = aktualisierung.nachsehen(werte.get("update_repo", ""), VERSION)
        ergebnis["eigene"] = VERSION
        ablage.einstellungen_speichern({"update_stand": ergebnis})
        return jsonify(ergebnis)

    @app.post("/api/lebt")
    def lebt():
        """Lebenszeichen der Oberfläche. Bleibt es aus, beendet sich das Programm."""
        return jsonify({"ok": True})

    @app.get("/api/version")
    def version():
        return jsonify({"programm": "PTA Inventarisierung", "version": VERSION,
                        "ordner": str(ablage.ordner)})

    return app
