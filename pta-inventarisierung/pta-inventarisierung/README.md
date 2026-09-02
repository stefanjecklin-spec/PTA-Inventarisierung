# PTA Inventarisierung

Prüf- und Abschlusskontrolle für die FTTH-Ausbaudokumentation. Das Programm führt
pro Projekt durch 19 Prüfpunkte, erinnert an offene Nachkontrollen und erkennt,
ob sich Spleissreport, BEP-Report, Kabeleinzugsplan oder Situationsplan gegenüber
dem Original verändert haben.

Läuft vollständig offline auf dem eigenen Rechner. Es werden keine Daten
übermittelt; der Dienst hört ausschliesslich auf `127.0.0.1`.

---

## Was es kann

**Prüfliste.** 19 Punkte in acht Gruppen: Ausbaumodell und OTO, Verteilgehäuse und
Spleissung, Kabel, Rohre und Hauseinführung, Erdstrecken und Lage, Schächte,
Inbetriebnahme, Dokumente und Abschluss. Jeder Punkt bekommt einen Stand — offen,
i.O., Nacharbeit oder nicht relevant — dazu Bemerkung, Messwert und ein Datum für
die Nachkontrolle.

Eigene Prüfpunkte lassen sich ergänzen, wahlweise **nur für das laufende Projekt**
oder **dauerhaft für alle Projekte**. Dauerhafte Punkte landen im Katalog in
`zustand.json` und erscheinen automatisch in jedem neuen Projekt — und sofort auch
in den bereits offenen, dort mit dem Stand «offen». Entfernen geht am Punkt selbst;
bei einem dauerhaften Punkt wird nachgefragt, weil dabei die erfassten Stände in
allen Projekten wegfallen. Beim Sichern eines Projektarchivs wird der Katalog
mitgeschrieben und beim Laden auf einem anderen Rechner ergänzt.

**Erinnerungen.** Ist eine Nachkontrolle fällig, meldet sich das Programm beim
Start mit einem Fenster, das alle heute fälligen und alle überfälligen Punkte
auflistet — einmal pro Tag, und bei laufendem Programm auch über Mitternacht
hinweg. Wer Benachrichtigungen erlaubt, bekommt zusätzlich eine Windows-Meldung.
Die Übersicht zeigt daneben überschrittene Abschlusstermine und offene
Nacharbeiten über alle Projekte hinweg; die Anzahl steht im Fenstertitel.
«Projekt abschliessen» zählt vorher auf, was noch fehlt.

**Dokumentenprüfung.** Vom Original werden SHA-256-Fingerabdruck, Grösse,
Seitenzahl und der lesbare Text gespeichert, dazu eine Kopie der Datei. Wird später
die revidierte Fassung eingelesen, meldet das Programm unverändert oder verändert
und zeigt bei lesbarem Text die geänderten Zeilen. Wird eine Änderung erkannt,
springt der Prüfpunkt «Situationen angepasst» automatisch auf Nacharbeit zurück.

Ein erfasstes Dokument lässt sich jederzeit anpassen:

| Schaltfläche | Wirkung |
|---|---|
| Original ersetzen | neue Datei als Vergleichsgrundlage; fragt nach, wenn schon geprüft wurde, und verwirft dann das Prüfergebnis |
| Original entfernen | Fingerabdruck, Prüfstand und Revisionsverlauf löschen; das Dokument steht wieder leer bereit |
| Andere Datei prüfen | eine weitere Fassung gegen dasselbe Original halten |
| Als neues Original übernehmen | den geprüften Stand zur künftigen Vergleichsgrundlage machen — vollständig, ohne erneutes Einlesen |
| Prüfung verwerfen | nur das Ergebnis löschen; Original und Verlauf bleiben |

Der Revisionsverlauf bleibt bei all dem erhalten und hält fest, welche Fassung wann
mit welchem Ergebnis geprüft wurde.

Nicht jede gefundene Stelle ist von Belang. Über **nicht relevant** verschwindet
eine Stelle samt ihrem Rahmen aus der Übersicht; die Auswahl wird gespeichert und
lässt sich jederzeit rückgängig machen. Ausgeblendete Stellen erscheinen auch nicht
im gedruckten Protokoll.

**Eigener Prüfablauf.** Die acht Gruppen der Prüfliste lassen sich am Griff
verschieben oder mit den Pfeilen umordnen, sodass die Reihenfolge dem eigenen
Kontrollgang entspricht. Ein Klick auf den Gruppentitel klappt eine Gruppe zu — die
Kopfzeile zeigt dann weiterhin, wie viele Punkte darin offen sind. Reihenfolge und
zugeklappte Gruppen gelten für alle Projekte und bleiben gespeichert;
«Reihenfolge zurücksetzen» stellt den Auslieferungszustand her.

Textauswertung funktioniert bei PDF (über `pypdf`), Word, Excel, PowerPoint und
allen Klartextformaten.

**Pläne ohne Textebene.** Situations- und Kabeleinzugspläne aus GIS- und
CAD-Systemen bestehen oft nur aus einem Bild je Seite — es gibt keinen Text zum
Vergleichen. Für diese Fälle rendert das Programm beide Fassungen und vergleicht
sie Bildpunkt für Bildpunkt. Das Ergebnis besteht aus zwei Teilen:

* eine **Übersicht** der ganzen Seite, auf der die veränderten Stellen umrahmt und
  nummeriert sind. Die Rahmen liegen als Ebene über dem Bild, der Plan selbst bleibt
  unberührt und vollständig lesbar. Ein Klick auf einen Rahmen springt zur
  zugehörigen Vergrösserung.
* je Stelle ein **Ausschnitt in hoher Auflösung** (rund 360 dpi), links das
  Original, rechts der aktuelle Stand. Beschriftungen, Muffentypen und Masse
  lassen sich direkt ablesen.

Zwei Vorkehrungen halten Fehlalarme fern. Eine Toleranz von zwei Bildpunkten fängt
ab, dass ein neu erzeugtes PDF dieselbe Zeichnung minim versetzt rastert — ohne sie
würde jede Linie des Plans aufleuchten. Und vor dem Vergleich wird ein Versatz der
ganzen Seite erkannt und ausgeglichen: wird ein Plan neu exportiert, sitzt die
Zeichnung oft einige Bildpunkte daneben, und ohne Ausgleich meldet der Vergleich
den Blattrahmen als Änderung — einen dünnen Streifen über die ganze Seitenhöhe.
Der erkannte Versatz wird in der Oberfläche ausgewiesen; ein schmaler Saum am
Blattrand bleibt unbewertet.

Weichen die Seitenformate voneinander ab, rechnet der Vergleich sie auf dieselbe
Grösse und weist ausdrücklich darauf hin, dass er dadurch ungenauer wird.
Benachbarte Fundstellen werden eng gefasst und erst beim Zeichnen um ihr Umfeld
erweitert, damit nicht der halbe Plan in einem einzigen Kasten landet.

Dafür sind `pypdfium2` und `Pillow` nötig. Fehlen sie, arbeitet das Programm ohne
Bildvergleich weiter und meldet das im Selbsttest.

**Abgleich mit dem PTA-AM.** Im Reiter *PTA-AM* liest das Programm die
Komponentenliste `…_Komponentenliste_….xml` ein. Daraus entsteht eine
Arbeitsliste: jedes Objekt, dessen `change-status` nicht `unset` ist, hat einen
Änderungsauftrag und lässt sich einzeln abhaken. Solange dort etwas offen ist,
wurde eine Anpassung noch nicht erledigt — «Projekt abschliessen» zählt das mit auf.

**Arbeitsarten.** Vor oder während der Bearbeitung kreuzt du an, was du im PTA
anpasst: Trassee anpassen, KS Neubau, KS anpassen, Neubau von Rohren, Kabeleinzug
mit Datum, HAK ausbauen nach BEP-Report. Jede Arbeitsart nennt die Objektarten, die
in der Komponentenliste erscheinen müssen. Nach dem Einlesen prüft das Programm:

* **Angekreuzt, aber kein passendes Objekt geändert** — rot. Entweder wurde die
  Anpassung im PTA vergessen, oder die Arbeitsart trifft nicht zu.
* **Geändert, aber keiner Arbeitsart zugeordnet** — es fehlt ein Kreuz, oder im PTA
  wurde etwas geändert, das nicht vorgesehen war.
* **Objekte ohne Länge** — bei Rohranlagen und LWL-Kabeln führt die Liste eine
  Länge; fehlt sie, wurde im PTA etwas nicht fertig erfasst.

Was die Datei **nicht** hergibt, steht als ausdrückliche Bestätigung dabei. Die
Komponentenliste enthält je Objekt nur Kennung, Typ, Änderungsstand und teils eine
Länge — **keine Datumsangaben**. Das Einzugsdatum beim Kabeleinzug und das
Ausbaudatum beim HAK lassen sich daraus nicht prüfen. Sie erscheinen deshalb als
gelbe Punkte «bitte im PTA nachsehen und bestätigen» und werden beim Abschluss
namentlich aufgezählt, solange sie nicht abgehakt sind.

**Mitwachsen.** Die Arbeitsarten stehen nicht fest im Programm — über
«+ Eigene Arbeitsart» legst du weitere an, wählst die zugehörigen Objektarten aus
oder erfasst neue, und schreibst die Bestätigungspunkte selbst. Sie gelten für alle
Projekte und lassen sich jederzeit bearbeiten oder auf die Vorgabe zurücksetzen.

Zwei Meldungen helfen dabei, nichts zu übersehen. Enthält eine Liste ein
Kennungspräfix, das das Programm nicht kennt, wird das gemeldet — die Objekte
erscheinen dann mit ihrem Typ statt einer Objektart. Und liefert das PTA in einer
Datei Felder mit, die noch nicht ausgewertet werden, steht das ebenfalls da, samt
Feldnamen. Genau daraus lassen sich später echte Prüfungen bauen, etwa auf ein
Datum.

**Der Abgleich.** Zusätzlich: Am Ende des Arbeitsgangs — Dokumente
geprüft, Anpassungen im PTA erfasst — wird die Liste einmal hereingezogen und in
beide Richtungen gegengehalten.

* **Notiert, aber im PTA nicht angepasst.** Kennungen, die im Projekt vorkommen,
  im PTA aber keinen Änderungsstand tragen. Genau hier geht eine Anpassung
  verloren. Das erscheint rot und wird beim Abschluss aufgezählt.
* **Im PTA angepasst, im Projekt nicht vermerkt.** Zum Gegenlesen — muss kein
  Fehler sein, da nicht jede Anpassung im Plan sichtbar auffällt.
* **Deckungsgleich.** Was beidseits übereinstimmt, mit Angabe des Fundorts.

Woher die Kennungen kommen: aus jedem Feld «Objekt-Kennung» bei den geänderten
Planstellen, und automatisch aus allen Bemerkungen, Messwerten und der Projektnotiz
— erkannt wird das PTA-Muster aus drei Grossbuchstaben und sieben Zeichen, etwa
`CHA08wwdnd` oder `UGR090f84o`. Fliesstext wie «KS 0.6/0.8» löst keinen Treffer aus.

Ziehst du zwei Ausgaben derselben Liste nacheinander hinein, kommt zusätzlich der
Verlauf dazu: was seither erledigt ist, was neu dazukam, was verschwunden ist.

Kennungspräfixe werden in verständliche Gruppen übersetzt — CUC zu Rohranlage, CHA
zu Schacht, UGR zu Erdstrecke, FSC zu LWL-Kabel und so weiter. Die Datei ist in
windows-1252 kodiert; das wird aus der XML-Deklaration gelesen, Umlaute bleiben
korrekt.

**Protokoll.** Über «Protokoll drucken» entsteht das Prüfprotokoll mit
Unterschriftszeilen für Bearbeiter und Quality Manager.

---

## Installation

### Fertige Programmdatei (empfohlen)

1. Unter **Releases** die Datei `PTA-Inventarisierung.exe` herunterladen.
2. In einen eigenen Ordner legen, zum Beispiel `C:\PTA`.
3. Doppelklick. Es öffnet sich ein eigenes Programmfenster mit eigenem Symbol
   in der Taskleiste — kein Adressfeld, keine Lesezeichenleiste, kein
   Konsolenfenster.
4. Für Startmenü und Desktop einmalig `verknuepfung.bat` ausführen.

Die Daten landen im Unterordner `daten` neben der `.exe`. Zum Beenden einfach
das Fenster schliessen; das Programm merkt das und beendet sich mit.

Beim ersten Start meldet sich unter Umständen der SmartScreen-Filter, weil die
Datei nicht signiert ist. Über *Weitere Informationen → Trotzdem ausführen*
starten.

### Aus dem Quelltext

Voraussetzung: Python 3.11 oder neuer.

```bash
git clone https://github.com/DEIN-KONTO/pta-inventarisierung.git
cd pta-inventarisierung
pip install -r requirements.txt
python -m pta
```

Unter Windows genügt ein Doppelklick auf `start.bat`; die Umgebung wird beim
ersten Mal selbst eingerichtet.

### Aufrufparameter

| Parameter | Wirkung |
|---|---|
| `--daten D:\PTA\daten` | eigener Datenordner, etwa auf einem Netzlaufwerk |
| `--port 8731` | fester Port statt automatischer Suche |
| `--browser` | im normalen Browser öffnen statt im Programmfenster |
| `--fenster` | echtes Fenster ohne Browserprozess (braucht `pywebview`) |
| `--kein-fenster` | nur den Dienst starten, nichts öffnen |
| `--kein-autostop` | weiterlaufen, auch wenn das Fenster geschlossen wird |
| `--version` | Versionsnummer ausgeben |

Der Datenordner lässt sich auch über die Umgebungsvariable `PTA_DATEN` setzen.

---

## Wie das Fenster zustande kommt

Nein, es läuft nichts im Internet. Das Programm startet einen kleinen Dienst auf
`127.0.0.1` — diese Adresse bedeutet «dieser Computer» und ist von aussen nicht
erreichbar, auch nicht von anderen Geräten im selben Netz.

Die Oberfläche erscheint in einem Anwendungsfenster von Edge (`--app=`): eigenes
Fenster, kein Adressfeld, keine Lesezeichen. Es benutzt ein eigenes Profil im
Datenordner und ist damit vom normalen Browser unabhängig. Dieser Weg wurde
bewusst gewählt, weil dabei alle Fähigkeiten erhalten bleiben — vor allem das
Hineinziehen von Dateien aus dem Explorer.

Weil das Fenster technisch zu Edge gehört, zeigt die Taskleiste dessen Symbol.
Wer das nicht möchte, stellt über **Ansicht** in der Fusszeile auf
«Eigenständiges Fenster» um; dann übernimmt `pywebview` und es gibt keinen
Browserbezug mehr. Die Einstellung liegt in `daten/einstellungen.json` und gilt
ab dem nächsten Start.

Gesucht wird zuerst Edge, dann Chrome, dann Brave — und zwar über alle
Programmordner hinweg, nicht Ordner für Ordner. Sonst gewinnt Chrome aus
«Programme», weil Edge meist in «Programme (x86)» liegt.

Die Oberfläche meldet sich alle zwanzig Sekunden beim Dienst. Bleibt das
Lebenszeichen drei Minuten aus, weil das Fenster geschlossen wurde, beendet sich
das Programm selbst. Ein zweiter Doppelklick startet keinen zweiten Dienst,
sondern öffnet nur ein weiteres Fenster.

Wer ganz ohne Browserprozess arbeiten will, installiert `pywebview` und startet
mit `--fenster`. Dann entsteht ein echtes Fenster über die Windows-eigene
WebView2-Komponente. Zu beachten: je nach System lassen sich dort keine Dateien
per Ziehen ablegen — der Klick auf das Ablagefeld öffnet aber immer den
Dateidialog.

Netzverbindung braucht es genau einmal: beim ersten Start, wenn Flask, waitress
und pypdf geladen werden. Danach läuft alles offline. Die gepackte `.exe` bringt
diese Bibliotheken bereits mit und braucht auch das erste Mal kein Internet.

## Wo die Daten liegen

```
daten/
  zustand.json                     alle Projekte, Prüfstände, Termine, eigener Prüfkatalog
  einstellungen.json               Ansicht und bevorzugter Browser
  sicherungen/                     Tageskopien, die letzten 30 werden behalten
  texte/<fingerabdruck>.txt        ausgelesener Text je Dokumentfassung
  dokumente/<PJ>/<Dokument>/       Kopien der eingelesenen Dateien
  vergleiche/                      Markierungsbilder geänderter Planseiten
  fenster/                         Profil des Anwendungsfensters
  programm.log                     Meldungen, wenn keine Konsole da ist
```

Alles bleibt auf dem Rechner. Der Ordner `daten/` ist in `.gitignore` eingetragen
und gelangt nie ins Verzeichnis.

Sichern heisst: den Ordner `daten` kopieren. Für einzelne Projekte gibt es
zusätzlich «Archiv sichern», das eine JSON-Datei für den eigenen Projektordner
erzeugt und sich jederzeit wieder laden lässt.

Bei jedem Speichern schreibt das Programm zuerst eine temporäre Datei und
benennt sie erst danach um. Ein abgebrochener Schreibvorgang kann den Datenstand
darum nicht beschädigen. Wäre `zustand.json` trotzdem unlesbar, wird sie beiseite
gelegt und die jüngste Tagessicherung geladen.

---

## Auf GitHub stellen

Einmalig, im Projektordner:

```bash
git init
git add .
git commit -m "PTA Inventarisierung 1.0.0"
git branch -M main
```

Dann auf github.com ein leeres Verzeichnis anlegen — **ohne** README, Lizenz oder
.gitignore, die liegen bereits bei. Für Firmendaten das Verzeichnis auf *Private*
stellen. Anschliessend:

```bash
git remote add origin https://github.com/DEIN-KONTO/pta-inventarisierung.git
git push -u origin main
```

Ab jetzt baut GitHub bei jedem `git push` automatisch eine Windows-Programmdatei.
Sie liegt unter *Actions → letzter Lauf → Artifacts*.

Eine feste Version veröffentlichen:

```bash
git tag v1.9.0
git push origin v1.9.0
```

Damit erscheint die `.exe` unter *Releases* und lässt sich direkt herunterladen —
so kommt sie ohne Umweg auf andere Rechner.

### Kollegen automatisch über Neues informieren

Jede Installation kann täglich nachsehen, ob eine neuere Fassung bereitliegt.
Dazu unter **Einstellungen → Aktualisierung** das Verzeichnis eintragen, etwa
`meinkonto/pta-inventarisierung`. Das Programm fragt dann einmal pro Tag die
GitHub-Schnittstelle nach der jüngsten Veröffentlichung. Liegt eine neuere Fassung
vor, erscheint ein Fenster mit der Versionsnummer, den Freigabehinweisen und zwei
Schaltflächen: Programmdatei herunterladen und auf GitHub ansehen. Der Hinweis
erscheint je Fassung nur einmal, damit er nicht lästig wird.

Voraussetzungen: Das Verzeichnis muss für die Kollegen erreichbar sein — bei einem
privaten Verzeichnis funktioniert die Abfrage ohne Anmeldung nicht, dann ist es
entweder öffentlich zu stellen oder die Kollegen bekommen die Datei weiterhin von
Hand. Und jede Veröffentlichung braucht einen Tag der Form `v1.9.0`, weil daraus
die Versionsnummer gelesen wird.

Ohne Internet oder ohne eingetragenes Verzeichnis passiert schlicht nichts; das
Programm läuft unverändert weiter. Abschalten lässt sich die Prüfung im selben
Dialog.

Änderungen später:

```bash
git add .
git commit -m "Prüfpunkt Muffentyp ergänzt"
git push
```

---

## Aufbau

```
pta/
  __main__.py      Start: Port suchen, Dienst starten, Browser öffnen
  server.py        Flask-Schnittstelle, hört nur auf 127.0.0.1
  ablage.py        Datenordner, Zustandsdatei, Tagessicherungen
  dokumente.py     Fingerabdruck, Textextraktion, Zeilenvergleich
  bildvergleich.py seitenweiser Bildvergleich für Pläne ohne Textebene
  fenster.py       Programmfenster, Symbol, Meldungen ohne Konsole
  aktualisierung.py  fragt GitHub nach der jüngsten Veröffentlichung
  komponenten.py   liest und vergleicht die PTA-AM Komponentenliste
  static/
    index.html     gesamte Oberfläche, eine Datei ohne externe Bibliotheken
    icon.ico       Programmsymbol
    manifest.webmanifest, icon-192.png, icon-512.png
tests/
  test_pta.py      70 Tests für Auswertung, Ablage, Bildvergleich, Fenster und Schnittstelle
.github/workflows/
  build-windows.yml  Tests und Programmdatei bei jedem Stand
start.bat          Start der Quelltext-Fassung unter Windows
build.bat          erzeugt PTA-Inventarisierung.exe
verknuepfung.bat   legt Verknüpfungen im Startmenü und auf dem Desktop an
```

### Schnittstelle

| Aufruf | Zweck |
|---|---|
| `GET /api/zustand` | alle Projekte laden |
| `PUT /api/zustand` | Stand speichern |
| `POST /api/dokument` | Datei auswerten, als Original erfassen oder gegen das Original prüfen |
| `GET /api/vergleichsbild/<name>` | Übersicht oder Ausschnitt einer geänderten Planseite |
| `GET /api/selbsttest` | prüft Schreibrechte und vorhandene Bibliotheken |
| `POST /api/lebt` | Lebenszeichen des Fensters |
| `GET/PUT /api/einstellungen` | Ansicht, Browser, Aktualisierungsverzeichnis |
| `GET /api/update` | jüngste Veröffentlichung auf GitHub (höchstens täglich) |
| `POST /api/komponenten` | PTA-AM Komponentenliste lesen und gegen die vorige halten |
| `POST /api/ordner` | Ordner im Dateimanager öffnen |
| `POST /api/aufraeumen` | Texte ohne zugehöriges Dokument entfernen |
| `GET /api/version` | Version und Datenordner |

---

## Entwickeln

```bash
pip install -r requirements.txt pytest
pytest -q
```

Programmdatei selbst bauen — unter Windows genügt ein Doppelklick auf
`build.bat`. Das Ergebnis liegt danach unter `dist\PTA-Inventarisierung.exe`
und läuft ohne Installation.

Von Hand geht es so:

```bash
pip install pyinstaller
pyinstaller --onefile --name PTA-Inventarisierung ^
  --add-data "pta/static;static" --collect-submodules pypdf ^
  --hidden-import waitress --console run.py
```

Unter Linux und macOS steht statt des Semikolons ein Doppelpunkt:
`--add-data "pta/static:static"`. Gebaut wird immer auf dem Zielsystem —
eine Windows-`.exe` entsteht nur auf einem Windows-Rechner oder über den
GitHub-Ablauf, der genau dafür einen Windows-Rechner verwendet.

Neue Prüfpunkte gehören in `pta/static/index.html` in die Liste `CHECKS`; die
Gruppen stehen direkt darüber in `GROUPS`. Bestehende Projekte behalten dabei
ihren Stand, neue Punkte starten auf offen.

---

## Wenn der Start nicht klappt

**«Python wurde nicht gefunden» oder ein Hinweis auf den Microsoft Store.**
Windows liefert einen Platzhalter mit, der den Befehl `python` abfängt, bevor
ein echtes Python drankommt. Prüfen mit `py --version` in PowerShell. Kommt eine
Versionsnummer, ist Python da und `start.bat` findet es über den Launcher `py`.
Kommt eine Fehlermeldung, Python von [python.org](https://www.python.org/downloads/windows/)
installieren und dabei **Add python.exe to PATH** ankreuzen. Den Platzhalter kann
man zusätzlich abschalten unter *Einstellungen → Apps → Erweiterte
App-Einstellungen → App-Ausführungsaliase*.

**«Die Datei stammt aus dem Internet» oder ein blaues SmartScreen-Fenster.**
Rechtsklick auf die heruntergeladene ZIP-Datei → *Eigenschaften* → unten
*Zulassen* ankreuzen → *Übernehmen*, danach erst entpacken. Bei bereits
entpackten Dateien hilft in PowerShell im Projektordner:
`Get-ChildItem -Recurse | Unblock-File`

**«Die Umgebung konnte nicht angelegt werden.»**
Meist fehlen Schreibrechte, etwa in `C:\Programme` oder auf einem
Netzlaufwerk. Den Ordner nach `C:\PTA` verschieben.

**«Die benötigten Pakete konnten nicht geladen werden.»**
Beim ersten Start braucht es einmalig Internet, um Flask, waitress und pypdf zu
holen. Blockiert die Firma `pypi.org`, hilft die fertige `.exe` aus den Releases
— die bringt alles mit.

**«Auswertung fehlgeschlagen» beim Hineinziehen von Dokumenten.**
Das Programm nennt seit Version 1.0.1 den Grund im Meldungsfenster. Prüfe
zuerst, ob die Adresse im Browser mit der im Programmfenster übereinstimmt —
nach einem Neustart hört das Programm auf einem anderen Port, und ein alter
Browsertab erreicht es nicht mehr. F5 behebt das. Bleibt es dabei, öffnet F12
die Entwicklerkonsole; dort steht die genaue Ursache.

**«Die Einstellungen sind gerade nicht erreichbar» oder fehlende Funktionen.**
Dann sind Oberfläche und Programmdateien nicht auf demselben Stand. Beim
Aktualisieren immer den **ganzen Ordner `pta`** ersetzen, nicht nur
`pta/static/index.html` — neue Fassungen bringen oft auch neue Schnittstellen im
Python-Teil mit. Wer die Programmdatei verwendet, baut sie mit `build.bat` neu.
Seit 1.5.1 meldet sich das Programm beim Start von selbst, wenn die beiden Stände
auseinanderlaufen.

**Der Browser öffnet sich nicht.**
Die Adresse steht im Konsolenfenster, etwa `http://127.0.0.1:8731/`. Einfach
von Hand in Chrome oder Edge eingeben.

---

## Lizenz

MIT — siehe `LICENSE`.
