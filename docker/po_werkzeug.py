"""Kleines Werkzeug für die Übersetzungsdatei (ohne Zusatzpakete).

    python docker/po_werkzeug.py liste locale/en/LC_MESSAGES/django.po      # msgids als JSON
    python docker/po_werkzeug.py fuellen locale/en/LC_MESSAGES/django.po uebersetzungen.json
    python docker/po_werkzeug.py pruefen locale/en/LC_MESSAGES/django.po    # fehlende Übersetzungen
"""

import json
import re
import sys


def _str(zeilen):
    return "".join(json.loads(z) for z in zeilen)


def eintraege(text):
    """Zerlegt die .po-Datei in Blöcke mit msgid, msgid_plural und Übersetzungen."""
    bloecke = text.split("\n\n")
    ergebnis = []
    for block in bloecke:
        zeilen = block.splitlines()
        aktuell, daten, kommentare = None, {}, []
        for z in zeilen:
            if z.startswith("#"):
                kommentare.append(z)
                continue
            m = re.match(r'^(msgctxt|msgid_plural|msgid|msgstr(?:\[\d\])?) (".*")$', z)
            if m:
                aktuell = m.group(1)
                daten[aktuell] = [m.group(2)]
            elif z.startswith('"') and aktuell:
                daten[aktuell].append(z)
        if "msgid" in daten:
            ergebnis.append({"kommentare": kommentare, "daten": daten})
    return ergebnis


def _zeile(schluessel, wert):
    return f"{schluessel} {json.dumps(wert, ensure_ascii=False)}"


def schreiben(liste):
    teile = []
    for e in liste:
        d = e["daten"]
        z = list(e["kommentare"])
        for schluessel in ["msgctxt", "msgid", "msgid_plural"]:
            if schluessel in d:
                z.append(_zeile(schluessel, _str(d[schluessel])) if schluessel != "msgid" or _str(d["msgid"]) else 'msgid ""')
        for schluessel in sorted(k for k in d if k.startswith("msgstr")):
            wert = _str(d[schluessel])
            if "\n" in wert and not _str(d["msgid"]) == "":
                z.append(_zeile(schluessel, wert))
            elif _str(d["msgid"]) == "":
                z.append(f'{schluessel} ""')
                z.extend(json.dumps(t, ensure_ascii=False) for t in re.findall(r".*?\n", wert))
            else:
                z.append(_zeile(schluessel, wert))
        teile.append("\n".join(z))
    return "\n\n".join(teile) + "\n"


def main():
    befehl, pfad = sys.argv[1], sys.argv[2]
    with open(pfad, encoding="utf-8") as f:
        liste = eintraege(f.read())
    if befehl == "liste":
        print(json.dumps([[_str(e["daten"]["msgid"]), _str(e["daten"].get("msgid_plural", ['""']))]
                          for e in liste if _str(e["daten"]["msgid"])], ensure_ascii=False, indent=0))
    elif befehl == "fuellen":
        with open(sys.argv[3], encoding="utf-8") as f:
            uebersetzungen = json.load(f)
        for e in liste:
            d = e["daten"]
            msgid = _str(d["msgid"])
            if not msgid or msgid not in uebersetzungen:
                continue
            wert = uebersetzungen[msgid]
            if "msgid_plural" in d:
                einzahl, mehrzahl = wert if isinstance(wert, list) else (wert, wert)
                d["msgstr[0]"], d["msgstr[1]"] = [json.dumps(einzahl, ensure_ascii=False)], [json.dumps(mehrzahl, ensure_ascii=False)]
                d.pop("msgstr", None)
            else:
                d["msgstr"] = [json.dumps(wert, ensure_ascii=False)]
            e["kommentare"] = [k for k in e["kommentare"] if not k.startswith("#, fuzzy")]
        with open(pfad, "w", encoding="utf-8") as f:
            f.write(schreiben(liste))
    elif befehl == "pruefen":
        fehlend = []
        for e in liste:
            d = e["daten"]
            msgid = _str(d["msgid"])
            if not msgid:
                continue
            werte = [_str(v) for k, v in d.items() if k.startswith("msgstr")]
            if not all(werte) or any(k.startswith("#, fuzzy") for k in e["kommentare"]):
                fehlend.append(msgid)
        print(json.dumps(fehlend, ensure_ascii=False, indent=0))
        sys.exit(1 if fehlend else 0)


if __name__ == "__main__":
    main()
