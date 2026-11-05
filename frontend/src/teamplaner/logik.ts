/**
 * Reine Hilfsfunktionen des Teamplaners. Die Regeln entsprechen planung/kalender.py
 * (dort mit pytest getestet); hier dienen sie der sofortigen Anzeige während des Ziehens.
 */

import { sprache } from "../lib/i18n";
import { t } from "./texte";

// ---------- Datum (ISO-Strings "YYYY-MM-DD", gerechnet in UTC) ----------

export function parse(iso: string): Date {
  return new Date(`${iso}T00:00:00Z`);
}

export function iso(datum: Date): string {
  return datum.toISOString().slice(0, 10);
}

export function plusTage(isoDatum: string, tage: number): string {
  const d = parse(isoDatum);
  d.setUTCDate(d.getUTCDate() + tage);
  return iso(d);
}

/** Wochentag 0 = Montag … 6 = Sonntag */
export function wochentag(isoDatum: string): number {
  return (parse(isoDatum).getUTCDay() + 6) % 7;
}

export function istWochenende(isoDatum: string): boolean {
  return wochentag(isoDatum) >= 5;
}

export function montagVon(isoDatum: string): string {
  return plusTage(isoDatum, -wochentag(isoDatum));
}

export function tageZwischen(von: string, bis: string): string[] {
  const ergebnis: string[] = [];
  for (let d = von; d <= bis; d = plusTage(d, 1)) ergebnis.push(d);
  return ergebnis;
}

/** ISO-Kalenderwoche: Woche mit dem Donnerstag zählt. */
export function kalenderwoche(isoDatum: string): number {
  const d = parse(isoDatum);
  d.setUTCDate(d.getUTCDate() + 3 - wochentag(isoDatum));
  const jahresanfang = Date.UTC(d.getUTCFullYear(), 0, 1);
  return Math.ceil(((d.getTime() - jahresanfang) / 86400000 + 1) / 7);
}

export function kurzTag(isoDatum: string): string {
  return t("wochentage").split(",")[wochentag(isoDatum)];
}

export function kurzDatum(isoDatum: string): string {
  const [, m, tag] = isoDatum.split("-");
  return t("datum_kurz", { t: tag, m });
}

export function langDatum(isoDatum: string): string {
  const [j, m, tag] = isoDatum.split("-");
  return t("datum_lang", { t: tag, m, j });
}

export function zeitraumText(von: string, bis: string): string {
  return von === bis ? `${kurzTag(von)} ${langDatum(von)}` : `${kurzDatum(von)}–${langDatum(bis)}`;
}

// ---------- Einteilungsregeln ----------

export type Frei = Map<string, string>;

/** Tage, an denen eine Einteilung als eingeteilt zählt (siehe planung/kalender.py):
 * Wochenenden und Feiertage nur bei einer eintägigen Einteilung. */
export function zaehlendeTage(von: string, bis: string, frei: Frei): string[] {
  if (von === bis) return [von];
  return tageZwischen(von, bis).filter((d) => !istWochenende(d) && !frei.has(d));
}

export function abwesenheitsTage(von: string, bis: string): string[] {
  return tageZwischen(von, bis);
}

interface Zeitraum {
  person_id: number;
  von: string;
  bis: string;
}

/** Schlüssel "personId:datum" aller Tage mit mehr als einer Belegung. */
export function doppelbelegungen(einteilungen: Zeitraum[], abwesenheiten: Zeitraum[], frei: Frei): Set<string> {
  const zaehler = new Map<string, number>();
  const zaehlen = (schluessel: string) => zaehler.set(schluessel, (zaehler.get(schluessel) ?? 0) + 1);
  for (const e of einteilungen) zaehlendeTage(e.von, e.bis, frei).forEach((d) => zaehlen(`${e.person_id}:${d}`));
  for (const a of abwesenheiten) abwesenheitsTage(a.von, a.bis).forEach((d) => zaehlen(`${a.person_id}:${d}`));
  return new Set([...zaehler].filter(([, n]) => n > 1).map(([k]) => k));
}

// ---------- Rasterpositionen ----------

export interface Position {
  start: number; // erste sichtbare Spalte
  ende: number; // letzte sichtbare Spalte (inklusive)
  linksAbgeschnitten: boolean;
  rechtsAbgeschnitten: boolean;
}

/** Spaltenbereich eines Zeitraums in den sichtbaren Tagen, oder null wenn unsichtbar. */
export function position(von: string, bis: string, spalten: string[]): Position | null {
  if (spalten.length === 0) return null;
  const erste = spalten[0];
  const letzte = spalten[spalten.length - 1];
  if (bis < erste || von > letzte) return null;
  let start = spalten.findIndex((d) => d >= von);
  let ende = -1;
  for (let i = spalten.length - 1; i >= 0; i -= 1) {
    if (spalten[i] <= bis) {
      ende = i;
      break;
    }
  }
  if (start === -1 || ende === -1 || start > ende) return null;
  start = Math.max(0, start);
  return { start, ende, linksAbgeschnitten: von < erste, rechtsAbgeschnitten: bis > letzte };
}

/** Verteilt Balken auf Spuren, sodass sich in einer Spur nichts überlappt. */
export function spuren<T extends { position: Position }>(eintraege: T[]): T[][] {
  const sortiert = [...eintraege].sort(
    (a, b) => a.position.start - b.position.start || b.position.ende - a.position.ende,
  );
  const ergebnis: T[][] = [];
  const enden: number[] = [];
  for (const e of sortiert) {
    let spur = enden.findIndex((ende) => ende < e.position.start);
    if (spur === -1) {
      spur = ergebnis.length;
      ergebnis.push([]);
      enden.push(-1);
    }
    ergebnis[spur].push(e);
    enden[spur] = e.position.ende;
  }
  return ergebnis;
}

/** Neue Daten beim Verschieben um ``delta`` Spalten (= Tage, Wochenenden sind sichtbar). */
export function verschieben(von: string, bis: string, delta: number): { von: string; bis: string } {
  return { von: plusTage(von, delta), bis: plusTage(bis, delta) };
}

export function personentageText(eingeteilt: number, schaetzung: number | null): string {
  const zahl = (n: number) => (Number.isInteger(n) ? String(n) : n.toLocaleString(sprache() === "de" ? "de-AT" : "en-GB"));
  if (schaetzung === null) return t(eingeteilt === 1 ? "tag_anzahl" : "tage_anzahl", { n: zahl(eingeteilt) });
  return t("tage_von", { n: zahl(eingeteilt), s: zahl(schaetzung) });
}
