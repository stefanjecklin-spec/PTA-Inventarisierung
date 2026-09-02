"""Seitenweiser Bildvergleich fuer PDF ohne Textebene.

Plaene aus GIS- und CAD-Systemen enthalten oft nur Bilder. Ein Zeilenvergleich
greift dort nicht. Stattdessen wird jede Seite gerendert und Bildpunkt fuer
Bildpunkt verglichen.

Das Ergebnis besteht aus zwei Teilen:

* eine Uebersicht der ganzen Seite, auf der die veraenderten Stellen umrahmt
  und nummeriert sind. Der Plan bleibt dabei lesbar, es wird nichts uebermalt.
* je Stelle ein Ausschnitt in hoher Aufloesung, links das Original, rechts der
  aktuelle Stand. Dort lassen sich Beschriftungen und Masse direkt ablesen.

Braucht pypdfium2 und Pillow. Fehlen sie, meldet verfuegbar() False und das
Programm arbeitet ohne Bildvergleich weiter.
"""

from __future__ import annotations

import uuid
from collections import deque
from io import BytesIO
from pathlib import Path

SKALA_VERGLEICH = 1.4          # rund 100 dpi — schnell, reicht zum Auffinden
SKALA_UEBERSICHT = 2.2         # rund 160 dpi — Uebersicht der ganzen Seite
SKALA_AUSSCHNITT = 5.0         # rund 360 dpi — scharfe Ausschnitte zum Ablesen
AUSSCHNITT_MAX_BREITE = 1500   # Bildpunkte je Haelfte, begrenzt die Dateigroesse

MAX_SEITEN = 40
TINTE = 205                    # Grauwert, ab dem ein Bildpunkt als Zeichnung gilt
MELDESCHWELLE = 0.005          # Anteil in Prozent, ab dem eine Seite als geaendert gilt
TOLERANZ = 2                   # Bildpunkte Spielraum gegen Rasterverschiebungen
AUSRICHT_RADIUS = 10           # so weit wird nach einem Versatz der ganzen Seite gesucht
RANDMASKE = 6                  # Bildpunkte am Blattrand, die nicht bewertet werden

BLOCK = 18                     # Rastergroesse beim Zusammenfassen zu Stellen
BLOCKSCHWELLE = 10             # wie stark ein Raster­feld betroffen sein muss
MIN_GEWICHT = 60               # schwaechere Fundstellen gelten als Rauschen
RAND = 55                      # Bildpunkte Umfeld, das ein Ausschnitt mitzeigt
MAX_STELLEN = 12


def verfuegbar() -> bool:
    try:
        import pypdfium2  # noqa: F401
        import PIL  # noqa: F401
        return True
    except Exception:
        return False


# --------------------------------------------------------------------------
# Rendern
# --------------------------------------------------------------------------
def _oeffnen(quelle):
    import pypdfium2 as pdfium
    return pdfium.PdfDocument(quelle)


def _seite_grau(dok, nr: int, skala: float):
    return dok[nr].render(scale=skala).to_pil().convert("L")


def _seitenpaar(dok_alt, dok_neu, nr: int):
    """Rendert beide Fassungen einer Seite auf dieselbe Bildgroesse.

    Haben die Seiten unterschiedliche Masse, wird die Skala der neuen Fassung
    angepasst, statt das fertige Bild zu skalieren — Nachskalieren wuerde die
    Linien weichzeichnen und danach ueberall Unterschiede vortaeuschen.
    """
    from PIL import Image
    alt = _seite_grau(dok_alt, nr, SKALA_VERGLEICH)
    breite_alt = dok_alt[nr].get_size()[0]
    breite_neu = dok_neu[nr].get_size()[0]
    skala = SKALA_VERGLEICH * (breite_alt / breite_neu) if breite_neu else SKALA_VERGLEICH
    neu = _seite_grau(dok_neu, nr, skala)
    if neu.size != alt.size:
        neu = neu.resize(alt.size, Image.LANCZOS)
    return alt, neu


def _ausschnitt_rendern(dok, nr: int, anteile, skala: float):
    """Rendert nur einen Bildbereich, angegeben als Anteile der Seitenflaeche."""
    seite = dok[nr]
    breite_pt, hoehe_pt = seite.get_size()
    x0, y0, x1, y1 = anteile
    links = x0 * breite_pt
    rechts = (1.0 - x1) * breite_pt
    oben = y0 * hoehe_pt
    unten = (1.0 - y1) * hoehe_pt
    # pypdfium2 erwartet, wie viel an jeder Seite weggeschnitten wird
    return seite.render(scale=skala,
                        crop=(links, unten, rechts, oben)).to_pil().convert("RGB")


# --------------------------------------------------------------------------
# Vergleich auf Bildpunktebene
# --------------------------------------------------------------------------
def _tintenmaske(bild):
    return bild.point(lambda v: 255 if v < TINTE else 0)


def _punkte(maske) -> int:
    return sum(n for i, n in enumerate(maske.histogram()) if i > 127)


def _profil(maske, waagrecht: bool):
    """Verdichtet die Maske auf eine Zeile bzw. eine Spalte von Mittelwerten."""
    from PIL import Image
    # tobytes statt getdata: stabil und deutlich schneller
    if waagrecht:
        return list(maske.resize((maske.width, 1), Image.BOX).tobytes())
    return list(maske.resize((1, maske.height), Image.BOX).tobytes())


def _versatz_achse(a, b, radius: int) -> int:
    """Sucht die Verschiebung, bei der zwei Profile am besten uebereinstimmen."""
    n = min(len(a), len(b))
    if n <= 2 * radius + 2:
        return 0
    bester, bestwert = 0, None
    for d in range(-radius, radius + 1):
        summe = 0
        for i in range(radius, n - radius):
            summe += abs(a[i] - b[i + d])
        if bestwert is None or summe < bestwert:
            bestwert, bester = summe, d
    return bester


def _versatz_finden(maske_alt, maske_neu, radius: int = AUSRICHT_RADIUS):
    """Ermittelt, um wie viele Bildpunkte die ganze Seite verschoben ist.

    Wird ein Plan neu exportiert, sitzt die Zeichnung oft ein paar Bildpunkte
    daneben. Ohne Ausgleich meldet der Vergleich dann den Blattrahmen als
    Aenderung — einen duennen Streifen ueber die ganze Seitenhoehe.
    """
    dx = _versatz_achse(_profil(maske_alt, True), _profil(maske_neu, True), radius)
    dy = _versatz_achse(_profil(maske_alt, False), _profil(maske_neu, False), radius)
    return dx, dy


def _verschieben(bild, dx: int, dy: int):
    """Schiebt ein Bild um (-dx, -dy); frei werdende Raender werden Papier."""
    from PIL import Image
    if dx == 0 and dy == 0:
        return bild
    aus = Image.new(bild.mode, bild.size, 0)
    aus.paste(bild, (-dx, -dy))
    return aus


def _rand_ausblenden(maske, breite: int):
    """Setzt einen Streifen am Blattrand auf null — dort ist keine Aussage moeglich."""
    from PIL import ImageDraw
    if breite <= 0:
        return maske
    z = ImageDraw.Draw(maske)
    b, h = maske.size
    z.rectangle([0, 0, b - 1, breite - 1], fill=0)
    z.rectangle([0, h - breite, b - 1, h - 1], fill=0)
    z.rectangle([0, 0, breite - 1, h - 1], fill=0)
    z.rectangle([b - breite, 0, b - 1, h - 1], fill=0)
    return maske


def _masken(alt, neu, toleranz: int | None = None):
    """Liefert (entfernt, hinzu) als Schwarzweissmasken.

    Die Toleranz federt ab, dass ein neu erzeugtes PDF dieselbe Zeichnung um
    Bruchteile eines Bildpunktes versetzt rastert. Ohne sie leuchtet jede Linie
    des Plans auf.
    """
    from PIL import Image, ImageChops, ImageFilter
    if toleranz is None:
        toleranz = TOLERANZ
    if alt.size != neu.size:
        neu = neu.resize(alt.size, Image.LANCZOS)

    maske_alt, maske_neu = _tintenmaske(alt), _tintenmaske(neu)

    # Versatz der ganzen Seite ausgleichen, bevor verglichen wird
    dx, dy = _versatz_finden(maske_alt, maske_neu)
    if dx or dy:
        maske_neu = _verschieben(maske_neu, dx, dy)

    weiten = ImageFilter.MaxFilter(2 * toleranz + 1)
    entfernt = ImageChops.subtract(maske_alt, maske_neu.filter(weiten))
    hinzu = ImageChops.subtract(maske_neu, maske_alt.filter(weiten))

    saum = RANDMASKE + abs(dx) + abs(dy)
    entfernt = _rand_ausblenden(entfernt, saum)
    hinzu = _rand_ausblenden(hinzu, saum)
    return entfernt, hinzu, (dx, dy)


# --------------------------------------------------------------------------
# Fundstellen zusammenfassen
# --------------------------------------------------------------------------
def _stellen_finden(maske, breite: int, hoehe: int):
    """Fasst benachbarte veraenderte Bildpunkte zu Rechtecken zusammen."""
    from PIL import Image

    sp, ze = max(1, breite // BLOCK), max(1, hoehe // BLOCK)
    raster = maske.resize((sp, ze), Image.BOX).load()
    besucht = [[False] * sp for _ in range(ze)]
    gruppen = []

    for y in range(ze):
        for x in range(sp):
            if besucht[y][x] or raster[x, y] < BLOCKSCHWELLE:
                continue
            schlange = deque([(x, y)])
            besucht[y][x] = True
            zellen, gewicht = [], 0
            while schlange:
                cx, cy = schlange.popleft()
                zellen.append((cx, cy))
                gewicht += raster[cx, cy]
                for dx in (-1, 0, 1):
                    for dy in (-1, 0, 1):
                        nx, ny = cx + dx, cy + dy
                        if 0 <= nx < sp and 0 <= ny < ze and not besucht[ny][nx] \
                                and raster[nx, ny] >= BLOCKSCHWELLE:
                            besucht[ny][nx] = True
                            schlange.append((nx, ny))
            if gewicht < MIN_GEWICHT:
                continue
            xs = [c[0] for c in zellen]
            ys = [c[1] for c in zellen]
            # eng fassen — das Umfeld kommt erst beim Zeichnen dazu, sonst
            # wachsen benachbarte Fundstellen zu einem einzigen Klotz zusammen
            kasten = (min(xs) * BLOCK, min(ys) * BLOCK,
                      min(breite, (max(xs) + 1) * BLOCK),
                      min(hoehe, (max(ys) + 1) * BLOCK))
            gruppen.append((gewicht, kasten))

    gruppen = _zusammenlegen(gruppen)
    gruppen.sort(key=lambda g: -g[0])
    return [k for _, k in gruppen[:MAX_STELLEN]]


def _zusammenlegen(gruppen):
    """Legt Rechtecke zusammen, die sich nach dem Aufweiten ueberlappen."""
    geaendert = True
    while geaendert and len(gruppen) > 1:
        geaendert = False
        ergebnis = []
        offen = list(gruppen)
        while offen:
            gewicht, a = offen.pop()
            rest = []
            for g2, b in offen:
                if a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]:
                    a = (min(a[0], b[0]), min(a[1], b[1]),
                         max(a[2], b[2]), max(a[3], b[3]))
                    gewicht += g2
                    geaendert = True
                else:
                    rest.append((g2, b))
            offen = rest
            ergebnis.append((gewicht, a))
        gruppen = ergebnis
    return gruppen


# --------------------------------------------------------------------------
# Bilder erzeugen
# --------------------------------------------------------------------------
def _aufweiten(kasten, breite: int, hoehe: int, rand: int = RAND):
    """Umfeld um eine Fundstelle, damit der Ausschnitt im Zusammenhang steht."""
    x0, y0, x1, y1 = kasten
    return (max(0, x0 - rand), max(0, y0 - rand),
            min(breite, x1 + rand), min(hoehe, y1 + rand))


def _schrift(groesse: int):
    from PIL import ImageFont
    try:
        return ImageFont.load_default(size=groesse)
    except Exception:
        return ImageFont.load_default()


def _uebersicht_rendern(dok_neu, nr: int):
    """Die ganze Seite, unverändert und lesbar.

    Die Rahmen um die Fundstellen zeichnet die Oberfläche darüber. So lassen
    sie sich einzeln ausblenden, ohne dass das Bild neu erzeugt werden muss.
    """
    return dok_neu[nr].render(scale=SKALA_UEBERSICHT).to_pil().convert("RGB")


def _anteile(kasten, breite: int, hoehe: int):
    """Lage einer Fundstelle als Anteil der Seitenfläche, für die Anzeige."""
    x0, y0, x1, y1 = _aufweiten(kasten, breite, hoehe, 12)
    return [round(x0 / breite, 5), round(y0 / hoehe, 5),
            round(x1 / breite, 5), round(y1 / hoehe, 5)]


def _stelle_zeichnen(dok_alt, dok_neu, nr: int, kasten, groesse_vergleich, nummer: int):
    """Ausschnitt in hoher Aufloesung: links Original, rechts aktueller Stand."""
    from PIL import Image, ImageDraw

    breite_v, hoehe_v = groesse_vergleich
    x0, y0, x1, y1 = _aufweiten(kasten, breite_v, hoehe_v)
    anteile = (x0 / breite_v, y0 / hoehe_v, x1 / breite_v, y1 / hoehe_v)

    skala = SKALA_AUSSCHNITT
    breite_pt = dok_neu[nr].get_size()[0]
    erwartet = (anteile[2] - anteile[0]) * breite_pt * skala
    if erwartet > AUSSCHNITT_MAX_BREITE:
        skala = max(1.6, skala * AUSSCHNITT_MAX_BREITE / erwartet)

    links = _ausschnitt_rendern(dok_alt, min(nr, len(dok_alt) - 1), anteile, skala)
    rechts = _ausschnitt_rendern(dok_neu, nr, anteile, skala)
    if links.size != rechts.size:
        links = links.resize(rechts.size, Image.LANCZOS)

    b, h = rechts.size
    kopf, luecke, rahmen = 36, 18, 2
    tafel = Image.new("RGB", (b * 2 + luecke + rahmen * 4, h + kopf + rahmen * 2), "white")
    z = ImageDraw.Draw(tafel)
    schrift = _schrift(22)

    felder = ((links, f"Stelle {nummer}  |  Original", (200, 40, 30)),
              (rechts, f"Stelle {nummer}  |  aktueller Stand", (20, 130, 70)))
    for spalte, (bild, titel, farbe) in enumerate(felder):
        x = spalte * (b + luecke + rahmen * 2) + rahmen
        z.text((x, 7), titel, font=schrift, fill=farbe)
        tafel.paste(bild, (x, kopf))
        z.rectangle([x - rahmen, kopf - rahmen, x + b + rahmen - 1, kopf + h + rahmen - 1],
                    outline=farbe, width=rahmen)
    return tafel


def _format_hinweis(abweichend: bool, masse_alt, masse_neu) -> str | None:
    """Meldet abweichende Seitenformate — dann ist der Vergleich ungenauer."""
    if not abweichend:
        return None
    mm = lambda pt: round(pt * 25.4 / 72)
    return (f"Das Seitenformat weicht ab: Original {mm(masse_alt[0])}×{mm(masse_alt[1])} mm, "
            f"aktuell {mm(masse_neu[0])}×{mm(masse_neu[1])} mm. Der Vergleich rechnet die "
            f"Seiten auf dieselbe Grösse, wird dadurch aber ungenauer.")


# --------------------------------------------------------------------------
# Hauptfunktion
# --------------------------------------------------------------------------
def vergleichen(alt_quelle, neu_bytes: bytes, bildordner: Path) -> dict:
    """Vergleicht zwei PDF seitenweise als Bild.

    alt_quelle  Pfad zur abgelegten Kopie des Originals
    neu_bytes   Inhalt der neu eingelesenen Datei
    bildordner  Ordner fuer die erzeugten Bilder
    """
    if not verfuegbar():
        return {"moeglich": False, "grund": "pypdfium2 oder Pillow fehlt"}

    alt_pfad = Path(alt_quelle)
    if not alt_pfad.exists():
        return {"moeglich": False, "grund": "Die abgelegte Kopie des Originals fehlt"}

    try:
        dok_alt = _oeffnen(alt_pfad)
        dok_neu = _oeffnen(BytesIO(neu_bytes))
    except Exception as fehler:
        return {"moeglich": False, "grund": f"{fehler.__class__.__name__}: {fehler}"}

    from PIL import ImageChops

    bildordner.mkdir(parents=True, exist_ok=True)
    kennung = uuid.uuid4().hex[:10]
    seiten = []

    try:
        n_alt = min(len(dok_alt), MAX_SEITEN)
        n_neu = min(len(dok_neu), MAX_SEITEN)
        for nr in range(max(n_alt, n_neu)):
            if nr >= n_alt:
                seiten.append({"nr": nr + 1, "geaendert": True, "anteil": 100.0,
                               "hinweis": "Seite ist neu hinzugekommen",
                               "uebersicht": None, "stellen": []})
                continue
            if nr >= n_neu:
                seiten.append({"nr": nr + 1, "geaendert": True, "anteil": 100.0,
                               "hinweis": "Seite fehlt in der neuen Fassung",
                               "uebersicht": None, "stellen": []})
                continue

            masse_alt = dok_alt[nr].get_size()
            masse_neu = dok_neu[nr].get_size()
            format_abweichung = (abs(masse_alt[0] - masse_neu[0]) > 1
                                 or abs(masse_alt[1] - masse_neu[1]) > 1)

            alt, neu = _seitenpaar(dok_alt, dok_neu, nr)
            entfernt, hinzu, versatz = _masken(alt, neu)
            n_weg, n_dazu = _punkte(entfernt), _punkte(hinzu)
            flaeche = alt.size[0] * alt.size[1]
            anteil = round((n_weg + n_dazu) / flaeche * 100, 3) if flaeche else 0.0

            if anteil < MELDESCHWELLE:
                seiten.append({"nr": nr + 1, "geaendert": False, "anteil": anteil,
                               "entfernt": n_weg, "hinzu": n_dazu, "versatz": versatz,
                               "format": _format_hinweis(format_abweichung, masse_alt, masse_neu),
                               "uebersicht": None, "stellen": []})
                continue

            kaesten = _stellen_finden(ImageChops.lighter(entfernt, hinzu),
                                      alt.size[0], alt.size[1])

            uebersicht_name = None
            if kaesten:
                bild = _uebersicht_rendern(dok_neu, nr)
                uebersicht_name = f"{kennung}_s{nr + 1}.png"
                bild.save(bildordner / uebersicht_name, "PNG", optimize=True)

            stellen = []
            for i, kasten in enumerate(kaesten, start=1):
                try:
                    tafel = _stelle_zeichnen(dok_alt, dok_neu, nr, kasten, alt.size, i)
                except Exception:
                    continue
                name = f"{kennung}_s{nr + 1}x{i}.png"
                tafel.save(bildordner / name, "PNG", optimize=True)
                stellen.append({"nr": i, "bild": name,
                                "anteile": _anteile(kasten, alt.size[0], alt.size[1]),
                                "breite": tafel.size[0], "hoehe": tafel.size[1]})

            seiten.append({"nr": nr + 1, "geaendert": True, "anteil": anteil,
                           "entfernt": n_weg, "hinzu": n_dazu, "versatz": versatz,
                           "format": _format_hinweis(format_abweichung, masse_alt, masse_neu),
                           "uebersicht": uebersicht_name, "stellen": stellen})
    finally:
        for dok in (dok_alt, dok_neu):
            try:
                dok.close()
            except Exception:
                pass

    return {
        "moeglich": True,
        "seiten_alt": n_alt,
        "seiten_neu": n_neu,
        "seiten": seiten,
        "geaenderte_seiten": [s["nr"] for s in seiten if s["geaendert"]],
    }
