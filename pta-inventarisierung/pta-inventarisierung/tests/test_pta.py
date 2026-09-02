"""Tests fuer Dokumentauswertung, Ablage und Schnittstelle."""

import io
import json
import zipfile

import pytest

from pta import dokumente
from pta.ablage import Ablage
from pta.server import erzeuge_app


# --------------------------------------------------------------- Hilfsmittel
def mach_docx(text: str) -> bytes:
    puffer = io.BytesIO()
    with zipfile.ZipFile(puffer, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", "<Types/>")
        absaetze = "".join(f"<w:p><w:r><w:t>{z_}</w:t></w:r></w:p>" for z_ in text.split("\n"))
        z.writestr("word/document.xml", f"<w:document><w:body>{absaetze}</w:body></w:document>")
    return puffer.getvalue()


@pytest.fixture
def ablage(tmp_path):
    return Ablage(tmp_path / "daten")


@pytest.fixture
def client(ablage):
    app = erzeuge_app(ablage)
    app.config.update(TESTING=True)
    return app.test_client()


# --------------------------------------------------------------- Auswertung
def test_fingerabdruck_ist_stabil():
    a = dokumente.auswerten("a.txt", b"x" * 100)
    b = dokumente.auswerten("anders.txt", b"x" * 100)
    assert a["hash"] == b["hash"]
    assert len(a["hash"]) == 64
    assert a["hashAlg"] == "SHA-256"


def test_fingerabdruck_erkennt_aenderung():
    a = dokumente.auswerten("a.txt", b"Schacht A 60x60 " * 10)
    b = dokumente.auswerten("a.txt", b"Schacht A 80x80 " * 10)
    assert a["hash"] != b["hash"]


def test_text_aus_docx():
    daten = mach_docx("BEP-Report Stand 01.09.2026\nAnzahl SPL: 24")
    satz = dokumente.auswerten("bep.docx", daten)
    assert satz["textOk"]
    assert "Anzahl SPL: 24" in satz["_text"]


def test_klartext_wird_erkannt():
    inhalt = "Spleissreport\nMuffe FIST GCO2Bd\nDrop 12F\nMehrlaenge 8 m\n" * 3
    satz = dokumente.auswerten("report.csv", inhalt.encode())
    assert satz["textOk"]
    assert satz["pages"] is None


def test_binaerdaten_liefern_keinen_text():
    satz = dokumente.auswerten("plan.bin", bytes(range(256)) * 40)
    assert not satz["textOk"]
    assert satz["hash"]


def test_vergleich_gleich():
    satz = dokumente.auswerten("a.txt", b"Situationsplan Etappe 2 " * 8)
    ergebnis = dokumente.vergleichen(satz, "abc", satz, "abc")
    assert ergebnis["same"] is True
    assert ergebnis["diff"] is None


def test_vergleich_zeigt_geaenderte_zeilen():
    alt = "Schacht A 60x60\nMuffe FIST\nDrop 12F"
    neu = "Schacht A 80x80\nMuffe FIST\nDrop 12F\nMehrlaenge 8 m"
    a = dokumente.auswerten("a.txt", alt.encode())
    b = dokumente.auswerten("b.txt", neu.encode())
    ergebnis = dokumente.vergleichen(a, alt, b, neu)
    assert ergebnis["same"] is False
    assert ergebnis["diff"]["changed"] == 3
    arten = {r["t"] for r in ergebnis["diff"]["rows"]}
    assert "add" in arten and "del" in arten
    texte = [r["s"] for r in ergebnis["diff"]["rows"]]
    assert "Schacht A 80x80" in texte
    assert "Mehrlaenge 8 m" in texte


def test_seitenzahl_differenz():
    a = {"hash": "1", "size": 10, "pages": 4}
    b = {"hash": "2", "size": 25, "pages": 6, "name": "neu.pdf"}
    ergebnis = dokumente.vergleichen(a, None, b, None)
    assert ergebnis["pagesDelta"] == 2
    assert ergebnis["sizeDelta"] == 15
    assert ergebnis["diff"] is None       # ohne Text kein Zeilenvergleich


# --------------------------------------------------------------- Ablage
def test_zustand_wird_gespeichert(ablage):
    ablage.speichern({"v": 1, "projects": [{"id": "a", "pj": "PJ-1"}]})
    assert ablage.laden()["projects"][0]["pj"] == "PJ-1"


def test_tagessicherung_wird_angelegt(ablage):
    ablage.speichern({"v": 1, "projects": []})
    ablage.speichern({"v": 1, "projects": [{"id": "b"}]})
    assert list(ablage.sicherungen.glob("zustand_*.json"))


def test_defekte_datei_wird_beiseitegelegt(ablage):
    ablage.zustand_datei.write_text("{kein gueltiges json", encoding="utf-8")
    daten = ablage.laden()
    assert daten["projects"] == []
    assert list(ablage.ordner.glob("zustand_defekt_*.json"))


def test_dokumentkopie_wird_abgelegt(ablage):
    pfad = ablage.dokument_ablegen("PJ-1", "Spleissreport", "original", "plan.pdf", b"abc")
    assert pfad.endswith("plan.pdf")
    assert "PJ-1" in pfad


def test_aufraeumen_entfernt_verwaiste_texte(ablage):
    ablage.text_schreiben("aaa", "gebraucht")
    ablage.text_schreiben("bbb", "verwaist")
    daten = {"projects": [{"docs": [{"ref": {"hash": "aaa"}, "revisions": []}]}]}
    assert ablage.aufraeumen(daten) == 1
    assert ablage.text_lesen("aaa") == "gebraucht"
    assert ablage.text_lesen("bbb") is None


# --------------------------------------------------------------- Schnittstelle
def test_oberflaeche_wird_ausgeliefert(client):
    antwort = client.get("/")
    assert antwort.status_code == 200
    assert b"PTA Inventarisierung" in antwort.data


def test_zustand_lesen_und_schreiben(client):
    leer = client.get("/api/zustand").get_json()
    assert leer["projects"] == []
    assert leer["_ablage"]["ordner"]

    neu = {"v": 1, "projects": [{"id": "x1", "pj": "PJ-4711", "items": {}}]}
    assert client.put("/api/zustand", json=neu).status_code == 200
    assert client.get("/api/zustand").get_json()["projects"][0]["pj"] == "PJ-4711"


def test_ungueltiger_zustand_wird_abgewiesen(client):
    assert client.put("/api/zustand", json={"unsinn": True}).status_code == 400


def test_original_erfassen_und_pruefen(client):
    alt = b"Spleissreport\nSchacht A 60x60\nMuffe FIST\nDrop 12F\n"
    neu = b"Spleissreport\nSchacht A 80x80\nMuffe FIST\nDrop 12F\n"

    erst = client.post("/api/dokument", data={
        "datei": (io.BytesIO(alt), "spleiss.txt"),
        "art": "original", "projekt": "PJ-4711", "dokument": "Spleissreport",
    }, content_type="multipart/form-data").get_json()
    satz = erst["datensatz"]
    assert satz["textOk"] is True
    assert satz["pfad"]

    gleich = client.post("/api/dokument", data={
        "datei": (io.BytesIO(alt), "spleiss.txt"),
        "art": "pruefung", "projekt": "PJ-4711", "dokument": "Spleissreport",
        "referenz_hash": satz["hash"], "referenz_groesse": str(satz["size"]),
        "referenz_seiten": "",
    }, content_type="multipart/form-data").get_json()
    assert gleich["vergleich"]["same"] is True

    anders = client.post("/api/dokument", data={
        "datei": (io.BytesIO(neu), "spleiss_rev.txt"),
        "art": "pruefung", "projekt": "PJ-4711", "dokument": "Spleissreport",
        "referenz_hash": satz["hash"], "referenz_groesse": str(satz["size"]),
        "referenz_seiten": "",
    }, content_type="multipart/form-data").get_json()
    vergleich = anders["vergleich"]
    assert vergleich["same"] is False
    assert vergleich["diff"]["changed"] == 2
    assert any(r["s"] == "Schacht A 80x80" for r in vergleich["diff"]["rows"])


def test_dokument_ohne_datei(client):
    assert client.post("/api/dokument", data={}).status_code == 400


def test_version(client):
    daten = client.get("/api/version").get_json()
    assert daten["version"]
    assert daten["ordner"]


# --------------------------------------------------------------- Fehlerfaelle
def test_selbsttest_meldet_ok(client):
    daten = client.get("/api/selbsttest").get_json()
    assert daten["ok"] is True
    assert daten["probleme"] == []
    assert daten["pdf"] is True


def test_selbsttest_meldet_gesperrten_ordner(tmp_path):
    import os
    import stat
    ablage = Ablage(tmp_path / "gesperrt")
    os.chmod(ablage.texte, stat.S_IRUSR | stat.S_IXUSR)
    try:
        ergebnis = ablage.selbsttest()
        if os.getuid() != 0:                       # als root greift kein Schreibschutz
            assert ergebnis["ok"] is False
            assert any("texte" in p for p in ergebnis["probleme"])
    finally:
        os.chmod(ablage.texte, stat.S_IRWXU)


def test_leere_datei_wird_abgewiesen(client):
    antwort = client.post("/api/dokument", data={
        "datei": (io.BytesIO(b""), "leer.pdf"), "art": "original",
    }, content_type="multipart/form-data")
    assert antwort.status_code == 400
    assert "leer" in antwort.get_json()["fehler"].lower()


def test_fehlermeldung_ist_lesbar(client):
    antwort = client.post("/api/dokument", data={}, content_type="multipart/form-data")
    assert antwort.status_code == 400
    assert "Datei" in antwort.get_json()["fehler"]


def test_text_schreiben_stoert_nicht_bei_schreibschutz(tmp_path):
    import os
    import stat
    ablage = Ablage(tmp_path / "ro")
    os.chmod(ablage.texte, stat.S_IRUSR | stat.S_IXUSR)
    try:
        ablage.text_schreiben("abc", "Inhalt")     # darf keine Ausnahme werfen
    finally:
        os.chmod(ablage.texte, stat.S_IRWXU)


# --------------------------------------------------------------- Bildvergleich
def _plan_pdf(pfad, aenderung=False):
    """Erzeugt einen kleinen Testplan; mit aenderung=True eine abweichende Fassung."""
    PIL = pytest.importorskip("PIL")
    from PIL import Image, ImageDraw
    bild = Image.new("RGB", (600, 420), "white")
    z = ImageDraw.Draw(bild)
    z.rectangle([40, 40, 560, 380], outline="black", width=2)
    z.line([(80, 340), (300, 120), (520, 300)], fill="black", width=3)
    z.text((90, 60), "Situationsplan KOR_002")
    if aenderung:
        z.rectangle([320, 200, 480, 260], fill="black")
    bild.save(pfad, "PDF", resolution=120)
    return pfad


def test_bildvergleich_erkennt_gleiche_seite(tmp_path):
    pytest.importorskip("pypdfium2")
    from pta import bildvergleich
    plan = _plan_pdf(tmp_path / "plan.pdf")
    ergebnis = bildvergleich.vergleichen(plan, plan.read_bytes(), tmp_path / "bilder")
    assert ergebnis["moeglich"] is True
    assert ergebnis["geaenderte_seiten"] == []
    assert ergebnis["seiten"][0]["anteil"] == 0.0


def test_bildvergleich_findet_aenderung_und_legt_bilder_ab(tmp_path):
    pytest.importorskip("pypdfium2")
    from pta import bildvergleich
    alt = _plan_pdf(tmp_path / "alt.pdf")
    neu = _plan_pdf(tmp_path / "neu.pdf", aenderung=True)
    bilder = tmp_path / "bilder"
    ergebnis = bildvergleich.vergleichen(alt, neu.read_bytes(), bilder)
    assert ergebnis["geaenderte_seiten"] == [1]
    seite = ergebnis["seiten"][0]
    assert seite["anteil"] > 0.5
    assert seite["hinzu"] > seite["entfernt"]        # es wurde etwas ergaenzt
    assert (bilder / seite["uebersicht"]).exists()
    assert seite["stellen"], "es muss mindestens eine Fundstelle geben"
    for stelle in seite["stellen"]:
        assert (bilder / stelle["bild"]).exists()


def test_ausschnitt_zeigt_beide_fassungen_nebeneinander(tmp_path):
    pytest.importorskip("pypdfium2")
    from PIL import Image
    from pta import bildvergleich
    alt = _plan_pdf(tmp_path / "alt.pdf")
    neu = _plan_pdf(tmp_path / "neu.pdf", aenderung=True)
    bilder = tmp_path / "bilder"
    ergebnis = bildvergleich.vergleichen(alt, neu.read_bytes(), bilder)
    stelle = ergebnis["seiten"][0]["stellen"][0]
    bild = Image.open(bilder / stelle["bild"])
    # zwei Felder nebeneinander, also deutlich breiter als hoch
    assert bild.width > bild.height
    assert bild.width == stelle["breite"]


def test_fundstellen_bleiben_eng_gefasst(tmp_path):
    """Zwei weit auseinanderliegende Aenderungen duerfen nicht verschmelzen."""
    pytest.importorskip("pypdfium2")
    from PIL import Image, ImageDraw
    from pta import bildvergleich

    def plan(pfad, extra=False):
        b = Image.new("RGB", (1200, 800), "white")
        z = ImageDraw.Draw(b)
        z.rectangle([20, 20, 1180, 780], outline="black", width=2)
        if extra:
            z.rectangle([60, 60, 200, 160], fill="black")        # links oben
            z.rectangle([980, 620, 1140, 740], fill="black")     # rechts unten
        b.save(pfad, "PDF", resolution=120)
        return pfad

    alt = plan(tmp_path / "a.pdf")
    neu = plan(tmp_path / "b.pdf", extra=True)
    ergebnis = bildvergleich.vergleichen(alt, neu.read_bytes(), tmp_path / "b")
    assert len(ergebnis["seiten"][0]["stellen"]) == 2


def test_bildvergleich_ohne_kopie_meldet_grund(tmp_path):
    from pta import bildvergleich
    ergebnis = bildvergleich.vergleichen(tmp_path / "fehlt.pdf", b"%PDF-1.4", tmp_path / "b")
    assert ergebnis["moeglich"] is False
    assert "Kopie" in ergebnis["grund"] or "fehlt" in ergebnis["grund"]


def test_vergleichsbild_weist_fremde_pfade_ab(client):
    assert client.get("/api/vergleichsbild/../zustand.json").status_code in (400, 404)
    assert client.get("/api/vergleichsbild/boese.png").status_code == 400
    assert client.get("/api/vergleichsbild/abc123_s1x2.png").status_code == 404


def test_referenzpfad_ausserhalb_wird_ignoriert(ablage):
    assert ablage.ist_im_datenordner("/etc/passwd") is False
    pfad = ablage.dokument_ablegen("PJ-1", "Plan", "original", "p.pdf", b"%PDF-1.4")
    assert ablage.ist_im_datenordner(pfad) is True


# --------------------------------------------------------------- Programmfenster
def test_lebenszeichen_setzt_kontakt(client):
    import time as _t
    app = client.application
    app.letzter_kontakt = _t.time() - 500
    assert client.post("/api/lebt").get_json()["ok"] is True
    assert _t.time() - app.letzter_kontakt < 5


def test_jede_anfrage_gilt_als_lebenszeichen(client):
    import time as _t
    app = client.application
    app.letzter_kontakt = _t.time() - 500
    client.get("/api/version")
    assert _t.time() - app.letzter_kontakt < 5


def test_symbol_wird_ausgeliefert(client):
    antwort = client.get("/icon.ico")
    assert antwort.status_code == 200
    assert antwort.data[:4] == b"\x00\x00\x01\x00"        # ICO-Kennung


def test_oberflaeche_verweist_auf_symbol(client):
    assert b'rel="icon"' in client.get("/").data


def test_laeuft_schon_erkennt_leeren_port():
    from pta.__main__ import laeuft_schon, port_frei
    freier = 8999
    if port_frei(freier):
        assert laeuft_schon(freier) is False


def test_freier_port_liefert_freien_port():
    from pta.__main__ import freier_port, port_frei
    p = freier_port(8800)
    assert p == 0 or port_frei(p)


def test_browsersuche_stuerzt_nicht_ab():
    from pta.fenster import _browser_suchen
    ergebnis = _browser_suchen()
    assert ergebnis is None or isinstance(ergebnis, str)


def test_natives_fenster_meldet_false_ohne_pywebview():
    from pta import fenster
    import importlib.util
    if importlib.util.find_spec("webview") is None:
        assert fenster.natives_fenster("http://127.0.0.1:1/") is False


# --------------------------------------------------------------- Ansicht
def test_browsersuche_bevorzugt_edge_vor_chrome(monkeypatch, tmp_path):
    """Edge liegt meist in »Programme (x86)«, Chrome in »Programme«.
    Trotzdem muss Edge gewinnen."""
    import sys
    from pta import fenster

    edge = tmp_path / "x86/Microsoft/Edge/Application/msedge.exe"
    chrome = tmp_path / "pf/Google/Chrome/Application/chrome.exe"
    for datei in (edge, chrome):
        datei.parent.mkdir(parents=True, exist_ok=True)
        datei.write_text("")

    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(fenster.os, "environ", {
        "PROGRAMFILES": str(tmp_path / "pf"),
        "PROGRAMFILES(X86)": str(tmp_path / "x86"),
    })
    monkeypatch.setattr(fenster.shutil, "which", lambda _n: None)

    name, pfad = fenster._browser_suchen()
    assert name == "Microsoft Edge"
    assert pfad == str(edge)

    name, pfad = fenster._browser_suchen("chrome")      # erzwungen
    assert name == "Google Chrome"
    assert pfad == str(chrome)


def test_einstellungen_vorgabe_und_speichern(ablage):
    assert ablage.einstellungen_laden()["ansicht"] == "app"
    ablage.einstellungen_speichern({"ansicht": "fenster", "browser": "chrome"})
    werte = ablage.einstellungen_laden()
    assert werte["ansicht"] == "fenster"
    assert werte["browser"] == "chrome"


def test_einstellungen_weisen_unsinn_ab(ablage):
    assert ablage.einstellungen_speichern({"ansicht": "quatsch"})["ansicht"] == "app"
    ablage.einstellungen_speichern({"unbekannt": 1})
    assert "unbekannt" not in ablage.einstellungen_laden()


def test_einstellungen_ueber_schnittstelle(client):
    daten = client.get("/api/einstellungen").get_json()
    assert daten["ansicht"] == "app"
    assert "fenster_moeglich" in daten
    neu = client.put("/api/einstellungen", json={"ansicht": "browser"}).get_json()
    assert neu["ansicht"] == "browser"
    assert client.get("/api/einstellungen").get_json()["ansicht"] == "browser"


def test_beschaedigte_einstellungen_stoeren_nicht(ablage):
    ablage.einstellungen_datei.write_text("{kaputt", encoding="utf-8")
    assert ablage.einstellungen_laden()["ansicht"] == "app"


def test_manifest_und_symbole(client):
    daten = client.get("/manifest.webmanifest").get_json()
    assert daten["name"] == "PTA Inventarisierung"
    assert daten["display"] == "standalone"
    for symbol in daten["icons"]:
        assert client.get("/" + symbol["src"]).status_code == 200


def test_oberflaeche_verweist_auf_manifest(client):
    seite = client.get("/").data
    assert b'rel="manifest"' in seite
    assert b'application-name' in seite


def test_eigener_pruefkatalog_bleibt_erhalten(client):
    """Dauerhafte eigene Prüfpunkte werden mit dem Zustand gespeichert."""
    zustand = {
        "v": 1,
        "katalog": [{"id": "x1", "g": "g8", "t": "Trassee-Foto abgelegt",
                     "custom": True, "global": True}],
        "projects": [{"id": "p1", "pj": "PJ-1", "items": {}, "extra": [], "docs": [], "log": []}],
    }
    assert client.put("/api/zustand", json=zustand).status_code == 200
    gelesen = client.get("/api/zustand").get_json()
    assert gelesen["katalog"][0]["t"] == "Trassee-Foto abgelegt"
    assert gelesen["katalog"][0]["global"] is True
    assert gelesen["projects"][0]["extra"] == []


# --------------------------------------------------------------- Fassungsabgleich
def test_fassung_wird_in_die_oberflaeche_eingesetzt(client):
    seite = client.get("/").get_data(as_text=True)
    from pta.server import VERSION
    assert f"const DIENST_FASSUNG = '{VERSION}';" in seite
    assert "__FASSUNG__" not in seite


def test_oberflaeche_kennt_ihre_eigene_fassung(client):
    from pta.server import VERSION
    seite = client.get("/").get_data(as_text=True)
    assert f"const OBERFLAECHE_FASSUNG = '{VERSION}';" in seite, \
        "OBERFLAECHE_FASSUNG in index.html muss zur Programmfassung passen"


def test_version_meldet_dieselbe_fassung(client):
    from pta.server import VERSION
    assert client.get("/api/version").get_json()["version"] == VERSION


# --------------------------------------------------------------- Versatzausgleich
def _plan_versetzt(pfad, versatz=0, aenderung=False):
    """Erzeugt einen Testplan mit Blattrahmen, wahlweise versetzt."""
    PIL = pytest.importorskip("PIL")
    from PIL import Image, ImageDraw
    inhalt = Image.new("RGB", (1000, 700), "white")
    z = ImageDraw.Draw(inhalt)
    z.rectangle([12, 12, 987, 687], outline="black", width=3)      # Blattrahmen
    z.line([(120, 560), (420, 180), (760, 500)], fill="black", width=3)
    z.rectangle([200, 250, 340, 330], outline="black", width=2)
    if aenderung:
        z.rectangle([600, 200, 740, 300], fill="black")
    blatt = Image.new("RGB", inhalt.size, "white")
    blatt.paste(inhalt, (versatz, versatz))
    blatt.save(pfad, "PDF", resolution=120)
    return pfad


def test_versatz_erzeugt_keine_falschen_fundstellen(tmp_path):
    """Ein versetzt exportierter Plan darf nicht den Blattrahmen melden."""
    pytest.importorskip("pypdfium2")
    from pta import bildvergleich
    alt = _plan_versetzt(tmp_path / "alt.pdf", versatz=0)
    neu = _plan_versetzt(tmp_path / "neu.pdf", versatz=6)
    ergebnis = bildvergleich.vergleichen(alt, neu.read_bytes(), tmp_path / "b")
    seite = ergebnis["seiten"][0]
    assert seite["stellen"] == [], f"falsche Fundstellen: {seite['stellen']}"
    assert seite["versatz"] != (0, 0), "der Versatz muss erkannt werden"


def test_versatz_verdeckt_echte_aenderung_nicht(tmp_path):
    pytest.importorskip("pypdfium2")
    from pta import bildvergleich
    alt = _plan_versetzt(tmp_path / "alt.pdf", versatz=0)
    neu = _plan_versetzt(tmp_path / "neu.pdf", versatz=6, aenderung=True)
    ergebnis = bildvergleich.vergleichen(alt, neu.read_bytes(), tmp_path / "b")
    seite = ergebnis["seiten"][0]
    assert len(seite["stellen"]) == 1
    assert seite["hinzu"] > seite["entfernt"]


def test_gleiche_datei_meldet_keinen_versatz(tmp_path):
    pytest.importorskip("pypdfium2")
    from pta import bildvergleich
    plan = _plan_versetzt(tmp_path / "plan.pdf")
    ergebnis = bildvergleich.vergleichen(plan, plan.read_bytes(), tmp_path / "b")
    seite = ergebnis["seiten"][0]
    assert seite["versatz"] == (0, 0)
    assert seite["geaendert"] is False


def test_abweichendes_seitenformat_wird_gemeldet(tmp_path):
    pytest.importorskip("pypdfium2")
    from PIL import Image, ImageDraw
    from pta import bildvergleich

    def plan(pfad, groesse):
        b = Image.new("RGB", groesse, "white")
        z = ImageDraw.Draw(b)
        z.rectangle([12, 12, groesse[0]-13, groesse[1]-13], outline="black", width=3)
        z.line([(100, 400), (400, 150)], fill="black", width=3)
        b.save(pfad, "PDF", resolution=120)
        return pfad

    alt = plan(tmp_path / "a.pdf", (1000, 700))
    neu = plan(tmp_path / "b.pdf", (1200, 840))
    ergebnis = bildvergleich.vergleichen(alt, neu.read_bytes(), tmp_path / "b")
    hinweis = ergebnis["seiten"][0]["format"]
    assert hinweis and "Seitenformat" in hinweis


# --------------------------------------------------------------- Aktualisierung
def test_fassungsvergleich():
    from pta.aktualisierung import ist_neuer, fassung_zerlegen
    assert ist_neuer("1.8.2", "v1.9.0") is True
    assert ist_neuer("1.8.2", "1.8.2") is False
    assert ist_neuer("1.8.2", "v1.8.1") is False
    assert ist_neuer("1.9.0", "1.10.0") is True          # zehn ist grösser als neun
    assert fassung_zerlegen("v2.0.1") == (2, 0, 1)
    assert fassung_zerlegen("") == (0,)


def test_repo_muss_form_haben():
    from pta.aktualisierung import repo_gueltig
    assert repo_gueltig("konto/verzeichnis") is True
    assert repo_gueltig("nur-ein-name") is False
    assert repo_gueltig("") is False


def test_update_ohne_verzeichnis(client):
    daten = client.get("/api/update").get_json()
    assert daten["ok"] is False
    assert "Verzeichnis" in daten["grund"]


def test_update_weist_falsches_verzeichnis_ab(client):
    client.put("/api/einstellungen", json={"update_repo": "unsinn"})
    daten = client.get("/api/update?jetzt=1").get_json()
    assert daten["ok"] is False
    assert "konto/verzeichnis" in daten["grund"]


def test_update_kann_abgeschaltet_werden(client):
    client.put("/api/einstellungen", json={"update_pruefen": False})
    daten = client.get("/api/update").get_json()
    assert daten.get("aus") is True


def test_update_merkt_sich_das_ergebnis(client):
    client.put("/api/einstellungen", json={"update_repo": "konto/nichtvorhanden"})
    client.get("/api/update?jetzt=1")
    stand = client.get("/api/einstellungen").get_json()["update_stand"]
    assert stand.get("geprueft")
    zweiter = client.get("/api/update").get_json()
    assert zweiter.get("aus_zwischenspeicher") is True    # kein zweiter Netzzugriff


# --------------------------------------------------------------- PTA-AM Liste
KOMPONENTEN_XML = b"""<?xml version="1.0" encoding="windows-1252" standalone="yes"?>
<changed_object_list>
\t<generic-data>
\t\t<date>02.09.2026</date>
\t\t<project><name>KOR_100305939_002</name><title></title>
\t\t\t<networks><network><number>71</number><short-name>SAN</short-name>
\t\t\t<name>Sarnen</name></network></networks></project>
\t\t<scheme><name>Planung 1</name><owner>TLUJEST1</owner>
\t\t<status id="Correction opened">Korrektur er\xf6ffnet</status></scheme>
\t</generic-data>
\t<objects>
\t\t<object><asset-id>CUC098e542</asset-id><type id="2 / 0.5 E">2 / 0.5 E</type>
\t\t<change-status id="active_modify">Zu \xe4ndern (Aktiv)</change-status>
\t\t<foreign>False</foreign><length unit="m">26.87</length></object>
\t\t<object><asset-id>CHA08wwdnd</asset-id><type id="CH Control Manhole">KS Kontrollschacht</type>
\t\t<change-status id="active_modify_info">Zu \xe4ndern (Aktiv)</change-status>
\t\t<foreign>False</foreign></object>
\t\t<object><object-id class="point_of_interest">160215100</object-id>
\t\t<type id="Conduit End">Rohrende</type>
\t\t<change-status id="unset">unset</change-status><foreign>False</foreign></object>
\t</objects>
</changed_object_list>"""


def test_komponentenliste_wird_gelesen():
    from pta import komponenten
    daten = komponenten.lesen(KOMPONENTEN_XML)
    assert daten["kopf"]["projekt"] == "KOR_100305939_002"
    assert daten["kopf"]["netz"] == "Sarnen"
    assert daten["kopf"]["bearbeiter"] == "TLUJEST1"
    assert "eröffnet" in daten["kopf"]["schemastatus"]      # windows-1252 richtig gelesen
    assert daten["anzahl"] == 3
    assert daten["anzahlZuTun"] == 2                        # unset zählt nicht


def test_objekte_bekommen_verstaendliche_gruppen():
    from pta import komponenten
    objekte = {o["kennung"]: o for o in komponenten.lesen(KOMPONENTEN_XML)["objekte"]}
    assert objekte["CUC098e542"]["gruppe"] == "Rohranlage"
    assert objekte["CHA08wwdnd"]["gruppe"] == "Schacht"
    assert objekte["160215100"]["gruppe"] == "Trassenpunkt"
    assert objekte["CUC098e542"]["laenge"] == "26.87"
    assert objekte["CUC098e542"]["einheit"] == "m"


def test_fremde_datei_wird_abgewiesen():
    from pta import komponenten
    with pytest.raises(ValueError, match="kein gültiges XML"):
        komponenten.lesen(b"kein xml")
    with pytest.raises(ValueError, match="changed_object_list"):
        komponenten.lesen(b"<?xml version='1.0'?><etwas_anderes/>")


def test_vergleich_zweier_ausgaben():
    from pta import komponenten
    alt = komponenten.lesen(KOMPONENTEN_XML)
    neu = komponenten.lesen(KOMPONENTEN_XML.replace(
        b'<change-status id="active_modify">Zu \xe4ndern (Aktiv)</change-status>',
        b'<change-status id="unset">unset</change-status>', 1))
    v = komponenten.vergleichen(alt, neu)
    assert [o["kennung"] for o in v["erledigt"]] == ["CUC098e542"]
    assert [o["kennung"] for o in v["offen"]] == ["CHA08wwdnd"]
    assert v["alleErledigt"] is False


def test_vergleich_meldet_alles_erledigt():
    from pta import komponenten
    alt = komponenten.lesen(KOMPONENTEN_XML)
    fertig = KOMPONENTEN_XML.replace(b'id="active_modify_info"', b'id="unset"') \
                            .replace(b'id="active_modify"', b'id="unset"')
    v = komponenten.vergleichen(alt, komponenten.lesen(fertig))
    assert len(v["erledigt"]) == 2
    assert v["alleErledigt"] is True


def test_komponenten_ueber_schnittstelle(client):
    antwort = client.post("/api/komponenten", data={
        "datei": (io.BytesIO(KOMPONENTEN_XML), "liste.xml"), "projekt": "KOR_002",
    }, content_type="multipart/form-data")
    assert antwort.status_code == 200
    liste = antwort.get_json()["liste"]
    assert liste["anzahlZuTun"] == 2
    assert liste["pfad"]                                    # Kopie wurde abgelegt


def test_komponenten_schnittstelle_weist_fremdes_ab(client):
    antwort = client.post("/api/komponenten", data={
        "datei": (io.BytesIO(b"<falsch/>"), "x.xml"),
    }, content_type="multipart/form-data")
    assert antwort.status_code == 400
    assert "changed_object_list" in antwort.get_json()["fehler"]


def test_unbekannte_praefixe_werden_gemeldet():
    from pta import komponenten
    abgewandelt = KOMPONENTEN_XML.replace(b"<asset-id>CUC098e542</asset-id>",
                                          b"<asset-id>XYZ012abcd</asset-id>")
    daten = komponenten.lesen(abgewandelt)
    assert daten["unbekanntePraefixe"] == ["XYZ"]
    assert komponenten.lesen(KOMPONENTEN_XML)["unbekanntePraefixe"] == []


def test_neue_felder_werden_gemeldet():
    """Liefert das PTA künftig mehr Angaben, darf das nicht lautlos wegfallen."""
    from pta import komponenten
    mit_datum = KOMPONENTEN_XML.replace(
        b"<foreign>False</foreign><length unit=\"m\">26.87</length>",
        b"<foreign>False</foreign><install-date>01.09.2026</install-date>"
        b"<length unit=\"m\">26.87</length>")
    daten = komponenten.lesen(mit_datum)
    assert "install-date" in daten["neueFelder"]
    assert komponenten.lesen(KOMPONENTEN_XML)["neueFelder"] == []


def test_gruppen_werden_aufgelistet():
    from pta import komponenten
    gruppen = komponenten.lesen(KOMPONENTEN_XML)["gruppen"]
    assert "Rohranlage" in gruppen and "Schacht" in gruppen and "Trassenpunkt" in gruppen
