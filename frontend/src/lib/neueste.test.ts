import { describe, expect, it } from "vitest";
import { abgebrochen, Neueste } from "./neueste";

/** Antwort, die erst auf Zuruf eintrifft, und die wie fetch auf den Abbruch reagiert. */
function anfrage<T>(signal: AbortSignal) {
  let antworten!: (wert: T) => void;
  const antwort = new Promise<T>((ok, fehler) => {
    antworten = ok;
    signal.addEventListener("abort", () => fehler(new DOMException("abgebrochen", "AbortError")));
  });
  return { antwort, antworten };
}

/** Lädt wie Gantt.tsx: Antwort nur übernehmen, wenn die Anfrage noch die jüngste ist. */
function lader() {
  const neueste = new Neueste();
  const stand: { daten: string | null; fehler: string[] } = { daten: null, fehler: [] };
  const offen: { antworten: (wert: string) => void }[] = [];
  const laden = async () => {
    const { signal, aktuell } = neueste.starten();
    const a = anfrage<string>(signal);
    offen.push(a);
    try {
      const daten = await a.antwort;
      if (aktuell()) stand.daten = daten;
    } catch (f) {
      if (aktuell() && !abgebrochen(f)) stand.fehler.push(String(f));
    }
  };
  return { neueste, stand, offen, laden };
}

describe("Neueste", () => {
  it("übernimmt nur die Antwort der jüngsten Anfrage, auch wenn die ältere später eintrifft", async () => {
    const { stand, offen, laden } = lader();
    const erste = laden();
    const zweite = laden();
    offen[1].antworten("Stand nach der zweiten Änderung");
    await zweite;
    offen[0].antworten("Stand nach der ersten Änderung"); // überholt
    await erste;
    expect(stand.daten).toBe("Stand nach der zweiten Änderung");
    expect(stand.fehler).toEqual([]);
  });

  it("bricht die laufende Anfrage ab, ohne Fehlermeldung", async () => {
    const { neueste, stand, laden } = lader();
    const erste = laden();
    neueste.abbrechen();
    await erste;
    expect(stand).toEqual({ daten: null, fehler: [] });
  });

  it("ohne Überholen bleibt alles beim Alten", async () => {
    const { stand, offen, laden } = lader();
    const erste = laden();
    offen[0].antworten("eins");
    await erste;
    const zweite = laden();
    offen[1].antworten("zwei");
    await zweite;
    expect(stand.daten).toBe("zwei");
  });

  it("erkennt nur Abbrüche als abgebrochen", () => {
    expect(abgebrochen(new DOMException("x", "AbortError"))).toBe(true);
    expect(abgebrochen(new Error("Netzwerk"))).toBe(false);
    expect(abgebrochen(null)).toBe(false);
  });
});
