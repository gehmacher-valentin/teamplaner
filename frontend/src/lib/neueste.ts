/**
 * Von mehreren Ladeanfragen, die sich überholen können, gilt nur die jüngste: Antworten älterer
 * Anfragen werden verworfen, auch wenn sie später eintreffen, und die laufende Anfrage wird
 * abgebrochen, sobald eine neue startet. Sonst könnte nach zwei schnellen Änderungen ein alter
 * Stand stehen bleiben.
 */
export class Neueste {
  private nr = 0;
  private laufend: AbortController | null = null;

  /** Neue Anfrage: ``signal`` an fetch übergeben, vor dem Übernehmen der Antwort ``aktuell()`` prüfen. */
  starten(): { signal: AbortSignal; aktuell: () => boolean } {
    this.laufend?.abort();
    const steuerung = new AbortController();
    this.laufend = steuerung;
    const nr = ++this.nr;
    return { signal: steuerung.signal, aktuell: () => nr === this.nr };
  }

  /** Laufende Anfrage verwerfen, z. B. wenn die Ansicht wechselt oder die Seite verlassen wird. */
  abbrechen() {
    this.laufend?.abort();
    this.laufend = null;
    this.nr++;
  }
}

/** Fehler einer abgebrochenen Anfrage: kein Grund für eine Fehlermeldung. */
export function abgebrochen(fehler: unknown): boolean {
  return typeof fehler === "object" && fehler !== null && (fehler as { name?: string }).name === "AbortError";
}
