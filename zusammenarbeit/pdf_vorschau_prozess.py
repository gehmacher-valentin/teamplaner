"""Kindprozess der PDF-Vorschau: liest ein PDF von stdin und schreibt die erste Seite als WebP nach stdout.

Läuft getrennt von der Anwendung (``python -I``, ohne Django, ohne Umgebungsvariablen), aufgerufen von
``zusammenarbeit.pdf_vorschau``. PDFs sind fremde Dateien: Bevor irgendetwas gelesen wird, begrenzt der
Prozess seine Rechenzeit, seinen Speicher und das Schreiben von Dateien selbst. Bei jedem Fehler endet er
mit einem Rückgabewert ungleich 0 und schreibt nichts nach stdout.

Aufruf: ``python -I pdf_vorschau_prozess.py CPU_SEKUNDEN SPEICHER_MB BREITE MAX_HOEHE``
"""

import resource
import sys


def grenzen_setzen(cpu_sekunden, speicher_mb):
    resource.setrlimit(resource.RLIMIT_CPU, (cpu_sekunden, cpu_sekunden + 1))  # SIGXCPU, eine Sekunde später SIGKILL
    speicher = speicher_mb * 1024 * 1024
    resource.setrlimit(resource.RLIMIT_AS, (speicher, speicher))
    resource.setrlimit(resource.RLIMIT_FSIZE, (0, 0))  # keine Dateien schreiben (stdout ist eine Pipe)
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))


def erste_seite(daten, breite, max_hoehe):
    """Oberer Teil der ersten Seite, ``breite`` Pixel breit und höchstens ``max_hoehe`` hoch (PIL-Bild)."""
    import pypdfium2 as pdfium

    pdf = pdfium.PdfDocument(daten)
    if len(pdf) < 1:
        raise ValueError("PDF ohne Seiten")
    seite = pdf[0]
    seiten_breite, seiten_hoehe = seite.get_size()
    if not (0 < seiten_breite < 1e5 and 0 < seiten_hoehe < 1e5):
        raise ValueError("ungültige Seitengröße")
    skala = breite / seiten_breite
    sichtbar = min(seiten_hoehe, max_hoehe / skala)  # nur der obere Teil, in PDF-Punkten
    bitmap = seite.render(scale=skala, crop=(0, seiten_hoehe - sichtbar, 0, 0),
                          fill_color=(255, 255, 255, 255), draw_annots=True)
    return bitmap.to_pil().convert("RGB")


def main(argumente):
    cpu_sekunden, speicher_mb, breite, max_hoehe = (int(a) for a in argumente)
    grenzen_setzen(cpu_sekunden, speicher_mb)
    daten = sys.stdin.buffer.read()
    bild = erste_seite(daten, breite, max_hoehe)
    if bild.width > breite or bild.height > max_hoehe:  # sollte nie vorkommen, aber nie größer als erlaubt
        bild.thumbnail((breite, max_hoehe))
    bild.save(sys.stdout.buffer, "WEBP", quality=80, method=4)
    sys.stdout.buffer.flush()


if __name__ == "__main__":
    try:
        main(sys.argv[1:5])
    except BaseException as fehler:  # noqa: BLE001 – jeder Fehler heißt: keine Vorschau
        sys.stderr.write(f"{type(fehler).__name__}: {fehler}"[:500])
        sys.exit(1)
