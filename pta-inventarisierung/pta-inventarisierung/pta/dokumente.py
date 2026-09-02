"""Fingerabdruck, Textextraktion und Vergleich von Projektdokumenten.

Alles läuft lokal. Es werden keine Daten nach aussen gesendet.
"""

from __future__ import annotations

import difflib
import hashlib
import re
import zipfile
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path

TEXT_ENDUNGEN = {
    ".txt", ".csv", ".tsv", ".xml", ".json", ".md", ".svg", ".gml",
    ".dxf", ".kml", ".log", ".asc", ".sos", ".itf", ".yml", ".yaml",
}
ZIP_ENDUNGEN = {".docx", ".dotx", ".xlsx", ".xlsm", ".pptx", ".odt", ".ods"}

MAX_TEXT = 900_000
DIFF_MAX_ZEILEN = 6000
DIFF_MAX_ROWS = 900


def jetzt() -> str:
    return datetime.now(timezone.utc).isoformat()


# --------------------------------------------------------------------------
# Fingerabdruck
# --------------------------------------------------------------------------
def fingerabdruck(daten: bytes) -> str:
    return hashlib.sha256(daten).hexdigest()


# --------------------------------------------------------------------------
# Textextraktion
# --------------------------------------------------------------------------
def _pdf_auswerten(daten: bytes) -> tuple[int | None, str | None]:
    """Seitenzahl und Text eines PDF. Gibt (seiten, text) zurueck."""
    try:
        from pypdf import PdfReader
    except ImportError:
        return None, None
    try:
        reader = PdfReader(BytesIO(daten))
        if reader.is_encrypted:
            try:
                reader.decrypt("")
            except Exception:
                return None, None
        seiten = len(reader.pages)
        teile = []
        for seite in reader.pages[:400]:
            try:
                teile.append(seite.extract_text() or "")
            except Exception:
                teile.append("")
        text = "\n".join(teile).strip()
        return seiten, (text if len(text) > 25 else None)
    except Exception:
        return None, None


def _zip_auswerten(daten: bytes) -> str | None:
    """Text aus Office-Dateien holen. Sie sind ZIP-Archive mit XML darin."""
    try:
        zf = zipfile.ZipFile(BytesIO(daten))
    except Exception:
        return None
    bevorzugt = re.compile(
        r"(word/document\.xml|xl/sharedStrings\.xml|xl/worksheets/sheet\d+\.xml"
        r"|ppt/slides/slide\d+\.xml|content\.xml)$"
    )
    namen = [n for n in zf.namelist() if bevorzugt.search(n)]
    if not namen:
        namen = [n for n in zf.namelist() if n.endswith(".xml")][:40]
    teile = []
    for name in namen[:80]:
        try:
            roh = zf.read(name)
        except Exception:
            continue
        if len(roh) > 8_000_000:
            continue
        xml = roh.decode("utf-8", errors="replace")
        xml = re.sub(r"</w:p>|</a:p>|</text:p>|</row>|</c:v>", "\n", xml)
        xml = re.sub(r"<[^>]+>", " ", xml)
        xml = (xml.replace("&lt;", "<").replace("&gt;", ">")
                  .replace("&amp;", "&").replace("&apos;", "'").replace("&quot;", '"'))
        xml = re.sub(r"[ \t]{2,}", " ", xml)
        teile.append(xml)
    text = re.sub(r"\n{3,}", "\n\n", "\n".join(teile)).strip()
    return text if len(text) > 25 else None


def _klartext(daten: bytes) -> str | None:
    probe = daten[:65536]
    if b"\x00" in probe:
        return None
    steuerzeichen = sum(1 for b in probe if b < 9 or 13 < b < 32 or b == 127)
    if probe and steuerzeichen / len(probe) > 0.02:
        return None
    for kodierung in ("utf-8", "cp1252", "latin-1"):
        try:
            text = daten.decode(kodierung)
            break
        except UnicodeDecodeError:
            continue
    else:
        return None
    if text.count("\ufffd") > len(text) * 0.02:
        return None
    text = text.strip()
    return text if len(text) > 25 else None


def auswerten(dateiname: str, daten: bytes) -> dict:
    """Erzeugt den Datensatz zu einer Datei: Fingerabdruck, Groesse, Text."""
    endung = Path(dateiname).suffix.lower()
    seiten: int | None = None
    text: str | None = None

    if endung == ".pdf" or daten[:5] == b"%PDF-":
        seiten, text = _pdf_auswerten(daten)
    elif endung in ZIP_ENDUNGEN or daten[:2] == b"PK":
        text = _zip_auswerten(daten)
    elif endung in TEXT_ENDUNGEN or len(daten) < 4_000_000:
        text = _klartext(daten)

    if text:
        text = text.replace("\r\n", "\n").replace("\r", "\n")[:MAX_TEXT]

    return {
        "name": dateiname,
        "size": len(daten),
        "hash": fingerabdruck(daten),
        "hashAlg": "SHA-256",
        "pages": seiten,
        "textOk": bool(text),
        "at": jetzt(),
        "_text": text,
    }


# --------------------------------------------------------------------------
# Vergleich
# --------------------------------------------------------------------------
def _zeilen(text: str) -> list[str]:
    roh = [z.strip() for z in text.split("\n")]
    return [z for z in roh if z][:DIFF_MAX_ZEILEN]


def textvergleich(alt: str, neu: str) -> dict:
    a, b = _zeilen(alt), _zeilen(neu)
    gekuerzt = (len(alt.split("\n")) > DIFF_MAX_ZEILEN
                or len(neu.split("\n")) > DIFF_MAX_ZEILEN)
    matcher = difflib.SequenceMatcher(None, a, b, autojunk=False)
    rows: list[dict] = []
    geaendert = 0

    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            block = a[i1:i2]
            if len(block) <= 2:
                rows += [{"t": "ctx", "s": z} for z in block]
            else:
                rows.append({"t": "ctx", "s": block[0]})
                rows.append({"t": "gap", "s": "···"})
                rows.append({"t": "ctx", "s": block[-1]})
        else:
            if tag in ("delete", "replace"):
                for z in a[i1:i2]:
                    rows.append({"t": "del", "s": z})
                    geaendert += 1
            if tag in ("insert", "replace"):
                for z in b[j1:j2]:
                    rows.append({"t": "add", "s": z})
                    geaendert += 1

    return {"changed": geaendert, "trunc": gekuerzt, "rows": rows[:DIFF_MAX_ROWS]}


def vergleichen(referenz: dict, ref_text: str | None,
                aktuell: dict, akt_text: str | None) -> dict:
    gleich = referenz.get("hash") == aktuell.get("hash")
    ergebnis = {
        "same": gleich,
        "name": aktuell["name"],
        "at": jetzt(),
        "sizeDelta": aktuell["size"] - referenz.get("size", 0),
        "pagesDelta": None,
        "diff": None,
    }
    if referenz.get("pages") is not None and aktuell.get("pages") is not None:
        ergebnis["pagesDelta"] = aktuell["pages"] - referenz["pages"]
    if not gleich and ref_text and akt_text:
        ergebnis["diff"] = textvergleich(ref_text, akt_text)
    return ergebnis
