"""Datenablage auf der Festplatte.

Aufbau des Datenordners:

    daten/
      zustand.json              alle Projekte, Pruefstaende, Termine
      einstellungen.json        Ansicht und andere Vorlieben
      sicherungen/              taegliche Kopien von zustand.json
      texte/<hash>.txt          extrahierter Text je Dokumentfassung
      dokumente/<projekt>/<dokument>/...   Kopien der eingelesenen Dateien
      vergleiche/<kennung>_s<nr>.png       Markierungsbilder geaenderter Planseiten
"""

from __future__ import annotations

import json
import os
import re
import shutil
import sys
import threading
from datetime import date, datetime
from pathlib import Path

SICHERUNGEN_BEHALTEN = 30


def standard_datenordner() -> Path:
    """Datenordner bestimmen. Mit PTA_DATEN laesst er sich frei setzen."""
    gesetzt = os.environ.get("PTA_DATEN")
    if gesetzt:
        return Path(gesetzt).expanduser().resolve()
    if getattr(sys, "frozen", False):          # als .exe gepackt
        return Path(sys.executable).parent / "daten"
    return Path.cwd() / "daten"


def sicherer_name(text: str, ersatz: str = "ohne_name") -> str:
    text = re.sub(r"[^\w\-. äöüÄÖÜ]", "", str(text or "")).strip()
    text = re.sub(r"\s+", "_", text)
    return text[:60] or ersatz


class Ablage:
    def __init__(self, ordner: Path | None = None):
        self.ordner = Path(ordner) if ordner else standard_datenordner()
        self.zustand_datei = self.ordner / "zustand.json"
        self.einstellungen_datei = self.ordner / "einstellungen.json"
        self.sicherungen = self.ordner / "sicherungen"
        self.texte = self.ordner / "texte"
        self.dokumente = self.ordner / "dokumente"
        self.vergleiche = self.ordner / "vergleiche"
        for p in (self.ordner, self.sicherungen, self.texte,
                  self.dokumente, self.vergleiche):
            p.mkdir(parents=True, exist_ok=True)
        self._sperre = threading.Lock()

    # ---------------- Zustand ----------------
    def laden(self) -> dict:
        if not self.zustand_datei.exists():
            return {"v": 1, "projects": []}
        try:
            with self.zustand_datei.open(encoding="utf-8") as f:
                daten = json.load(f)
            daten.setdefault("projects", [])
            return daten
        except Exception:
            # beschaedigte Datei beiseitelegen, damit nichts verloren geht
            kaputt = self.ordner / f"zustand_defekt_{datetime.now():%Y%m%d_%H%M%S}.json"
            try:
                shutil.copy2(self.zustand_datei, kaputt)
            except Exception:
                pass
            letzte = sorted(self.sicherungen.glob("zustand_*.json"))
            if letzte:
                try:
                    with letzte[-1].open(encoding="utf-8") as f:
                        return json.load(f)
                except Exception:
                    pass
            return {"v": 1, "projects": []}

    def speichern(self, daten: dict) -> None:
        with self._sperre:
            self._tagessicherung()
            temp = self.zustand_datei.with_suffix(".tmp")
            with temp.open("w", encoding="utf-8") as f:
                json.dump(daten, f, ensure_ascii=False, indent=1)
            temp.replace(self.zustand_datei)   # atomar, kein halb geschriebener Stand

    def _tagessicherung(self) -> None:
        if not self.zustand_datei.exists():
            return
        ziel = self.sicherungen / f"zustand_{date.today():%Y-%m-%d}.json"
        if ziel.exists():
            return
        try:
            shutil.copy2(self.zustand_datei, ziel)
        except Exception:
            return
        alt = sorted(self.sicherungen.glob("zustand_*.json"))
        for datei in alt[:-SICHERUNGEN_BEHALTEN]:
            datei.unlink(missing_ok=True)

    # ---------------- Einstellungen ----------------
    STANDARD_EINSTELLUNGEN = {
        "ansicht": "app",          # app | fenster | browser
        "browser": "",             # leer = Edge bevorzugen, sonst chrome oder brave
        "update_repo": "",         # GitHub-Verzeichnis, z. B. "meinkonto/pta-inventarisierung"
        "update_pruefen": True,    # taeglich nach einer neueren Fassung sehen
        "update_stand": {},        # letztes Ergebnis, damit nicht dauernd gefragt wird
    }

    def einstellungen_laden(self) -> dict:
        werte = dict(self.STANDARD_EINSTELLUNGEN)
        try:
            if self.einstellungen_datei.exists():
                with self.einstellungen_datei.open(encoding="utf-8") as f:
                    gelesen = json.load(f)
                if isinstance(gelesen, dict):
                    werte.update({k: v for k, v in gelesen.items() if k in werte})
        except Exception:
            pass
        return werte

    def einstellungen_speichern(self, werte: dict) -> dict:
        aktuell = self.einstellungen_laden()
        aktuell.update({k: v for k, v in (werte or {}).items()
                        if k in self.STANDARD_EINSTELLUNGEN})
        if aktuell["ansicht"] not in ("app", "fenster", "browser"):
            aktuell["ansicht"] = "app"
        aktuell["update_pruefen"] = bool(aktuell.get("update_pruefen"))
        aktuell["update_repo"] = str(aktuell.get("update_repo") or "").strip()
        if not isinstance(aktuell.get("update_stand"), dict):
            aktuell["update_stand"] = {}
        try:
            temp = self.einstellungen_datei.with_suffix(".tmp")
            with temp.open("w", encoding="utf-8") as f:
                json.dump(aktuell, f, ensure_ascii=False, indent=1)
            temp.replace(self.einstellungen_datei)
        except Exception:
            pass
        return aktuell

    # ---------------- Texte ----------------
    def text_schreiben(self, fingerabdruck: str, text: str | None) -> None:
        if not text:
            return
        try:
            ziel = self.texte / f"{fingerabdruck}.txt"
            if not ziel.exists():
                ziel.write_text(text, encoding="utf-8")
        except Exception:
            # Der Text ist nur eine Beigabe fuer den Zeilenvergleich.
            # Laesst er sich nicht ablegen, arbeitet das Programm weiter.
            pass

    def text_lesen(self, fingerabdruck: str | None) -> str | None:
        if not fingerabdruck:
            return None
        ziel = self.texte / f"{fingerabdruck}.txt"
        if ziel.exists():
            try:
                return ziel.read_text(encoding="utf-8")
            except Exception:
                return None
        return None

    # ---------------- Dokumentkopien ----------------
    def dokument_ablegen(self, projekt: str, dokument: str, art: str,
                         dateiname: str, daten: bytes) -> str:
        ziel_ordner = self.dokumente / sicherer_name(projekt) / sicherer_name(dokument)
        ziel_ordner.mkdir(parents=True, exist_ok=True)
        stempel = datetime.now().strftime("%Y-%m-%d_%H%M%S")
        ziel = ziel_ordner / f"{art}_{stempel}_{sicherer_name(dateiname, 'datei')}"
        ziel.write_bytes(daten)
        return str(ziel)

    def ist_im_datenordner(self, pfad: str | Path) -> bool:
        """Schuetzt davor, dass ein Pfad ausserhalb des Datenordners gelesen wird."""
        try:
            Path(pfad).resolve().relative_to(self.dokumente.resolve())
            return True
        except Exception:
            return False

    def projektordner(self, projekt: str) -> Path:
        ordner = self.dokumente / sicherer_name(projekt)
        ordner.mkdir(parents=True, exist_ok=True)
        return ordner

    # ---------------- Aufraeumen ----------------
    def selbsttest(self) -> dict:
        """Prueft, ob im Datenordner wirklich geschrieben werden kann."""
        probleme: list[str] = []
        for name, ordner in (("Datenordner", self.ordner),
                             ("Ordner »texte«", self.texte),
                             ("Ordner »dokumente«", self.dokumente),
                             ("Ordner »vergleiche«", self.vergleiche),
                             ("Ordner »sicherungen«", self.sicherungen)):
            try:
                ordner.mkdir(parents=True, exist_ok=True)
                probe = ordner / ".schreibtest"
                probe.write_text("ok", encoding="utf-8")
                probe.unlink()
            except Exception as fehler:
                probleme.append(f"{name}: {fehler.__class__.__name__} — {fehler}")

        try:
            import pypdf  # noqa: F401
            pdf_da = True
        except Exception:
            pdf_da = False
        if not pdf_da:
            probleme.append("pypdf fehlt — PDF werden nur am Fingerabdruck verglichen, "
                            "nicht am Text.")

        return {"ok": not probleme, "ordner": str(self.ordner),
                "pdf": pdf_da, "probleme": probleme}

    def aufraeumen(self, daten: dict) -> int:
        """Texte entfernen, auf die kein Dokument mehr verweist."""
        gebraucht: set[str] = set()
        for projekt in daten.get("projects", []):
            for dok in projekt.get("docs", []):
                ref = dok.get("ref") or {}
                if ref.get("hash"):
                    gebraucht.add(ref["hash"])
                for rev in dok.get("revisions", []):
                    if rev.get("hash"):
                        gebraucht.add(rev["hash"])
        entfernt = 0
        for datei in self.texte.glob("*.txt"):
            if datei.stem not in gebraucht:
                datei.unlink(missing_ok=True)
                entfernt += 1
        return entfernt
