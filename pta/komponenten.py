"""Komponentenliste aus dem PTA-AM lesen und vergleichen.

Die Datei »…_Komponentenliste_….xml« listet alle Objekte eines Schemas mit
ihrem Aenderungsstand. Objekte mit einem anderen Stand als ``unset`` sind zu
bearbeiten. Genau daraus wird eine Arbeitsliste: solange dort etwas offen ist,
wurde eine Anpassung noch nicht erledigt.

Zieht man spaeter eine neue Ausgabe derselben Liste hinein, zeigt der Vergleich,
was inzwischen erledigt ist, was weiterhin offen steht und was neu dazukam.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from datetime import datetime, timezone

# Staende, die Handlungsbedarf bedeuten. Alles andere gilt als ohne Auftrag.
OHNE_AUFTRAG = {"unset", "", None}

# Sprechende Namen fuer die Kennungspraefixe des PTA
PRAEFIXE = {
    "CUC": "Rohranlage",
    "COV": "Schachtabdeckung",
    "CHA": "Schacht",
    "UGR": "Erdstrecke",
    "FSC": "LWL-Kabel",
    "BEP": "BEP",
    "OTO": "OTO",
    "HAK": "Hausanschluss",
    "MUF": "Muffe",
}


def jetzt() -> str:
    return datetime.now(timezone.utc).isoformat()


# Felder, die diese Fassung auswertet. Alles andere wird gemeldet, damit
# auffaellt, wenn das PTA kuenftig mehr mitliefert — etwa Datumsangaben.
BEKANNTE_FELDER = {
    "asset-id", "object-id", "object-id@class", "type", "type@id",
    "change-status", "change-status@id", "foreign", "length", "length@unit",
}


def _klasse(kennung: str, klasse: str, typ: str) -> str:
    """Ordnet ein Objekt einer verständlichen Gruppe zu."""
    treffer = PRAEFIXE.get((kennung or "")[:3].upper())
    if treffer:
        return treffer
    if klasse:
        return {"point_of_interest": "Trassenpunkt",
                "figure_eight": "Kabelreserve"}.get(klasse, klasse.replace("_", " "))
    return typ or "Objekt"


def lesen(rohdaten: bytes) -> dict:
    """Liest eine Komponentenliste. Wirft ValueError, wenn es keine ist."""
    try:
        baum = ET.fromstring(rohdaten)          # Kodierung steht in der Datei
    except ET.ParseError as fehler:
        raise ValueError(f"Die Datei ist kein gültiges XML ({fehler}).") from fehler

    if baum.tag != "changed_object_list":
        raise ValueError("Das ist keine Komponentenliste aus dem PTA — erwartet wird "
                         f"»changed_object_list«, gefunden »{baum.tag}«.")

    kopf = {
        "datum": baum.findtext(".//generic-data/date") or "",
        "projekt": baum.findtext(".//project/name") or "",
        "titel": baum.findtext(".//project/title") or "",
        "netz": baum.findtext(".//network/name") or "",
        "netznummer": baum.findtext(".//network/number") or "",
        "schema": baum.findtext(".//scheme/name") or "",
        "bearbeiter": baum.findtext(".//scheme/owner") or "",
    }
    schemastatus = baum.find(".//scheme/status")
    kopf["schemastatus"] = schemastatus.text if schemastatus is not None else ""
    kopf["schemastatus_id"] = schemastatus.get("id", "") if schemastatus is not None else ""

    objekte = []
    for o in baum.findall(".//object"):
        asset = (o.findtext("asset-id") or "").strip()
        objekt_id_el = o.find("object-id")
        objekt_id = (objekt_id_el.text or "").strip() if objekt_id_el is not None else ""
        klasse = objekt_id_el.get("class", "") if objekt_id_el is not None else ""

        typ_el = o.find("type")
        status_el = o.find("change-status")
        laenge_el = o.find("length")

        kennung = asset or objekt_id
        status_id = status_el.get("id", "") if status_el is not None else ""
        objekte.append({
            "kennung": kennung,
            "asset": asset,
            "objektId": objekt_id,
            "klasse": klasse,
            "gruppe": _klasse(asset, klasse, typ_el.get("id", "") if typ_el is not None else ""),
            "typ": (typ_el.get("id") or typ_el.text or "") if typ_el is not None else "",
            "typText": (typ_el.text or "") if typ_el is not None else "",
            "statusId": status_id,
            "status": (status_el.text or "") if status_el is not None else "",
            "zuTun": status_id not in OHNE_AUFTRAG,
            "fremd": (o.findtext("foreign") or "").strip().lower() == "true",
            "laenge": (laenge_el.text or "").strip() if laenge_el is not None else "",
            "einheit": laenge_el.get("unit", "") if laenge_el is not None else "",
        })

    zu_tun = [o for o in objekte if o["zuTun"]]

    # Was diese Fassung nicht kennt — damit es auffaellt statt lautlos wegzufallen
    unbekannte_praefixe = sorted({
        o["asset"][:3].upper() for o in objekte
        if o["asset"] and o["asset"][:3].upper() not in PRAEFIXE
    })
    gesehene_felder = set()
    for o in baum.findall(".//object"):
        for kind in o:
            gesehene_felder.add(kind.tag)
            for merkmal in kind.attrib:
                gesehene_felder.add(f"{kind.tag}@{merkmal}")
    neue_felder = sorted(gesehene_felder - BEKANNTE_FELDER)

    return {
        "kopf": kopf,
        "objekte": objekte,
        "anzahl": len(objekte),
        "anzahlZuTun": len(zu_tun),
        "gruppen": sorted({o["gruppe"] for o in objekte if o["gruppe"]}),
        "unbekanntePraefixe": unbekannte_praefixe,
        "neueFelder": neue_felder,
        "gelesen": jetzt(),
    }


def vergleichen(alt: dict, neu: dict) -> dict:
    """Stellt zwei Ausgaben derselben Liste gegenüber.

    erledigt  stand vorher auf »zu ändern«, jetzt nicht mehr
    offen     steht weiterhin auf »zu ändern«
    neu       kam neu als »zu ändern« dazu
    weg       war vorher vorhanden, fehlt jetzt ganz
    """
    def nach_kennung(daten):
        return {o["kennung"]: o for o in daten.get("objekte", []) if o["kennung"]}

    a, b = nach_kennung(alt), nach_kennung(neu)
    erledigt, offen, neue, weg = [], [], [], []

    for kennung, objekt in a.items():
        jetzt_objekt = b.get(kennung)
        if jetzt_objekt is None:
            if objekt["zuTun"]:
                weg.append(objekt)
            continue
        if objekt["zuTun"] and not jetzt_objekt["zuTun"]:
            erledigt.append(jetzt_objekt)
        elif jetzt_objekt["zuTun"]:
            offen.append(jetzt_objekt)

    for kennung, objekt in b.items():
        if kennung not in a and objekt["zuTun"]:
            neue.append(objekt)

    return {
        "erledigt": erledigt, "offen": offen, "neu": neue, "weg": weg,
        "alleErledigt": not offen and not neue,
        "verglichen": jetzt(),
    }
