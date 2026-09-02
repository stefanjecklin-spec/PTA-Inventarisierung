"""Nachsehen, ob auf GitHub eine neuere Fassung bereitliegt.

Das Programm laeuft ohne Internet vollstaendig weiter. Diese Pruefung ist eine
Beigabe: schlaegt sie fehl, wird das gemeldet und sonst nichts unternommen.
Gefragt wird hoechstens einmal pro Tag.
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from datetime import date

ZEITGRENZE = 6          # Sekunden, dann wird abgebrochen
QUELLE = "https://api.github.com/repos/{repo}/releases/latest"


def fassung_zerlegen(text: str) -> tuple:
    """Wandelt »v1.9.0« in (1, 9, 0) — zum Vergleichen."""
    zahlen = re.findall(r"\d+", str(text or ""))
    return tuple(int(z) for z in zahlen[:4]) or (0,)


def ist_neuer(vorhanden: str, gefunden: str) -> bool:
    return fassung_zerlegen(gefunden) > fassung_zerlegen(vorhanden)


def repo_gueltig(repo: str) -> bool:
    return bool(re.fullmatch(r"[\w.-]+/[\w.-]+", (repo or "").strip()))


def nachsehen(repo: str, eigene_fassung: str) -> dict:
    """Fragt GitHub nach der neuesten Veroeffentlichung."""
    repo = (repo or "").strip()
    if not repo:
        return {"ok": False, "grund": "Kein GitHub-Verzeichnis hinterlegt.",
                "geprueft": date.today().isoformat()}
    if not repo_gueltig(repo):
        return {"ok": False, "grund": "Das Verzeichnis muss die Form »konto/verzeichnis« haben.",
                "geprueft": date.today().isoformat()}

    anfrage = urllib.request.Request(
        QUELLE.format(repo=repo),
        headers={"Accept": "application/vnd.github+json",
                 "User-Agent": "PTA-Inventarisierung"})
    try:
        with urllib.request.urlopen(anfrage, timeout=ZEITGRENZE) as antwort:
            daten = json.loads(antwort.read().decode("utf-8"))
    except urllib.error.HTTPError as fehler:
        grund = ("Im Verzeichnis gibt es noch keine Veröffentlichung."
                 if fehler.code == 404 else f"GitHub antwortete mit Fehler {fehler.code}.")
        return {"ok": False, "grund": grund, "geprueft": date.today().isoformat()}
    except Exception:
        return {"ok": False, "grund": "Keine Verbindung zu GitHub.",
                "geprueft": date.today().isoformat()}

    fassung = daten.get("tag_name") or daten.get("name") or ""
    datei = ""
    for anhang in daten.get("assets") or []:
        name = (anhang.get("name") or "").lower()
        if name.endswith(".exe"):
            datei = anhang.get("browser_download_url") or ""
            break

    return {
        "ok": True,
        "geprueft": date.today().isoformat(),
        "fassung": fassung.lstrip("vV"),
        "neuer": ist_neuer(eigene_fassung, fassung),
        "titel": daten.get("name") or fassung,
        "hinweise": (daten.get("body") or "")[:1200],
        "seite": daten.get("html_url") or f"https://github.com/{repo}/releases",
        "datei": datei,
        "veroeffentlicht": (daten.get("published_at") or "")[:10],
    }
