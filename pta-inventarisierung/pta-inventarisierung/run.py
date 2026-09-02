"""Einstiegspunkt für die gepackte Programmdatei.

Die .exe wird ohne Konsolenfenster gebaut. Damit ein Fehler beim Start nicht
unsichtbar bleibt, wird hier alles abgefangen, ins Protokoll geschrieben und
als Meldung angezeigt.
"""

import sys
import traceback


def main() -> int:
    try:
        from pta.__main__ import main as starten
        return starten()
    except Exception:
        spur = traceback.format_exc()
        ziel = "—"
        try:
            from pta.ablage import standard_datenordner
            ordner = standard_datenordner()
            ordner.mkdir(parents=True, exist_ok=True)
            ziel = ordner / "programm.log"
            with open(ziel, "a", encoding="utf-8") as f:
                f.write("\n--- Abbruch ---\n" + spur)
        except Exception:
            pass
        try:
            from pta.fenster import meldung
            meldung("PTA Inventarisierung — Start fehlgeschlagen",
                    f"Das Programm konnte nicht gestartet werden.\n\n"
                    f"{spur.strip().splitlines()[-1]}\n\n"
                    f"Einzelheiten stehen in:\n{ziel}")
        except Exception:
            print(spur)
        return 1


if __name__ == "__main__":
    sys.exit(main())
