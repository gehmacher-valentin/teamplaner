/** Reine Rechenfunktionen des Gantt-Diagramms (mit vitest getestet). */
import { parse, plusTage } from "../teamplaner/logik";
import type { GAbhaengigkeit, GAufgabe, GDaten, GWarnung, Zeile } from "./typen";

export const ZEILE = 34;
export const MASSSTAB = { woche: 30, monat: 12, quartal: 4 } as const;
export type Massstab = keyof typeof MASSSTAB;

export function tageZwischen(von: string, bis: string): number {
  return Math.round((parse(bis).getTime() - parse(von).getTime()) / 86400000);
}

/** x-Position (px) des Tagesbeginns relativ zum Beginn der Zeitachse. */
export function x(datum: string, start: string, px: number): number {
  return tageZwischen(start, datum) * px;
}

/** Balken von ``von`` bis ``bis`` (beide inklusive). */
export function balken(von: string, bis: string, start: string, px: number) {
  return { links: x(von, start, px), breite: (tageZwischen(von, bis) + 1) * px };
}

export function verschieben(datum: string | null, tage: number): string | null {
  return datum ? plusTage(datum, tage) : null;
}

/**
 * Sichtbare Zeilen: Projekte (einklappbar) mit ihren Aufgaben, danach externe Aufgaben.
 * Unteraufgaben stehen unter ihrer Hauptaufgabe, solange diese aufgeklappt ist (``aufgeklappt``).
 */
export function zeilen(
  daten: GDaten,
  zugeklappt: Set<number>,
  erledigteZeigen: boolean,
  aufgeklappt: (aufgabe: number) => boolean = () => true,
): Zeile[] {
  const ergebnis: Zeile[] = [];
  const sichtbar = (a: GAufgabe) => erledigteZeigen || !a.erledigt;
  for (const projekt of daten.projekte) {
    const zu = zugeklappt.has(projekt.id);
    ergebnis.push({ art: "projekt", projekt, zu });
    if (zu) continue;
    for (const id of projekt.aufgaben) {
      const aufgabe = daten.aufgaben[id];
      if (!aufgabe || !sichtbar(aufgabe)) continue;
      if (aufgabe.eltern && daten.aufgaben[aufgabe.eltern] && !aufgeklappt(aufgabe.eltern)) continue;
      ergebnis.push({ art: "aufgabe", aufgabe, zu: aufgabe.kinder.length > 0 && !aufgeklappt(aufgabe.id) });
    }
  }
  const extern = Object.values(daten.aufgaben).filter((a) => a.extern);
  if (extern.length) {
    ergebnis.push({ art: "extern" });
    extern.forEach((aufgabe) => ergebnis.push({ art: "aufgabe", aufgabe, zu: false }));
  }
  return ergebnis;
}

/**
 * Projektbalken: eingestellter Zeitraum (Beginn/Ende) und – wenn Aufgaben darüber hinaus geplant
 * sind – der Überzug davor bzw. danach. Ohne eingestellten Zeitraum zählen nur die Aufgaben.
 */
export function projektZeitraum(p: { beginn: string | null; ende: string | null; plan_von: string | null; plan_bis: string | null }) {
  const von = [p.beginn, p.plan_von].filter(Boolean).sort()[0] ?? null;
  const bis = [p.ende, p.plan_bis].filter(Boolean).sort().reverse()[0] ?? null;
  const vorne = p.beginn && p.plan_von && p.plan_von < p.beginn ? { von: p.plan_von, bis: plusTage(p.beginn, -1) } : null;
  const hinten = p.ende && p.plan_bis && p.plan_bis > p.ende ? { von: plusTage(p.ende, 1), bis: p.plan_bis } : null;
  return { von, bis, vorne, hinten };
}

export interface Pfeil {
  schluessel: string;
  von: number; // Zeilenindex
  nach: number;
  sx: number;
  tx: number;
  verletzt: boolean;
  abhaengigkeiten: GAbhaengigkeit[];
}

/** Rechtes bzw. linkes Ende einer Aufgabe (geplant, sonst tatsächlich). */
export function enden(a: GAufgabe): { anfang: string | null; ende: string | null } {
  const anfang = a.beginn ?? a.ist_von ?? a.ende;
  const ende = a.ende ?? a.ist_bis ?? a.beginn;
  return { anfang, ende };
}

/**
 * Wo eine Aufgabe in der Liste zu sehen ist: in ihrer eigenen Zeile, bei eingeklappten Unteraufgaben
 * in der Zeile der Hauptaufgabe, bei eingeklappten Projekten in der Projektzeile.
 */
function zeilenSuche(daten: GDaten, liste: Zeile[]) {
  const zeileAufgabe = new Map<number, number>();
  const zeileProjekt = new Map<number, number>();
  liste.forEach((z, i) => {
    if (z.art === "aufgabe") zeileAufgabe.set(z.aufgabe.id, i);
    if (z.art === "projekt") zeileProjekt.set(z.projekt.id, i);
  });
  /** Die sichtbare Aufgabe für ``a``: sie selbst oder ihre (aufgeklappte) Hauptaufgabe. */
  const sichtbar = (a: GAufgabe): GAufgabe | undefined => {
    if (zeileAufgabe.has(a.id)) return a;
    const eltern = a.eltern ? daten.aufgaben[a.eltern] : undefined;
    return eltern && zeileAufgabe.has(eltern.id) ? eltern : undefined;
  };
  const ziel = (a: GAufgabe) => {
    const s = sichtbar(a);
    return s ? zeileAufgabe.get(s.id) : zeileProjekt.get(a.projekt_id);
  };
  return { sichtbar, ziel };
}

/**
 * Warnungen „Einteilung verletzt Abhängigkeit“ je Zeilenindex. Sie stehen in der Zeile des
 * Nachfolgers und wandern wie die Pfeile nach oben, wenn diese Zeile eingeklappt ist; mehrere
 * Warnungen derselben Zeile werden zu einem Warnzeichen zusammengefasst.
 */
export function warnungenJeZeile(daten: GDaten, liste: Zeile[]): Map<number, GWarnung[]> {
  const { ziel } = zeilenSuche(daten, liste);
  const ergebnis = new Map<number, GWarnung[]>();
  for (const w of daten.warnungen ?? []) {
    const aufgabe = daten.aufgaben[w.aufgabe];
    const zeile = aufgabe ? ziel(aufgabe) : undefined;
    if (zeile === undefined) continue;
    ergebnis.set(zeile, [...(ergebnis.get(zeile) ?? []), w]);
  }
  return ergebnis;
}

/**
 * Pfeile für Abhängigkeiten. Eingeklappte Unteraufgaben zeigen auf ihre Hauptaufgabe, eingeklappte
 * Projekte auf die Projektzeile (zusammengefasst); innerhalb derselben Zeile entfallen sie.
 * Rot (``verletzt``) nur, wenn sich die geplanten Termine überschneiden: das ist im Diagramm zu
 * sehen und dort zu beheben. Verletzungen aus Einteilungen stehen als Warnzeichen in der Namensspalte.
 */
export function pfeile(daten: GDaten, liste: Zeile[], start: string, px: number): Pfeil[] {
  const { sichtbar, ziel } = zeilenSuche(daten, liste);
  const projektVon = (a: GAufgabe) => daten.projekte.find((p) => p.id === a.projekt_id);

  const gruppen = new Map<string, Pfeil>();
  for (const abh of daten.abhaengigkeiten) {
    const a = daten.aufgaben[abh.vorher];
    const b = daten.aufgaben[abh.nachher];
    if (!a || !b) continue;
    const von = ziel(a);
    const nach = ziel(b);
    if (von === undefined || nach === undefined || von === nach) continue;
    const sa = sichtbar(a);
    const sb = sichtbar(b);
    const endeA = sa ? enden(sa).ende : projektVon(a)?.ende ?? enden(a).ende;
    const anfangB = sb ? enden(sb).anfang : projektVon(b)?.beginn ?? enden(b).anfang;
    if (!endeA || !anfangB) continue;
    const schluessel = `${von}-${nach}`;
    const vorhanden = gruppen.get(schluessel);
    if (vorhanden) {
      vorhanden.abhaengigkeiten.push(abh);
      vorhanden.verletzt ||= abh.verletzt_plan;
      continue;
    }
    gruppen.set(schluessel, {
      schluessel, von, nach,
      sx: x(endeA, start, px) + px,
      tx: x(anfangB, start, px),
      verletzt: abh.verletzt_plan,
      abhaengigkeiten: [abh],
    });
  }
  return [...gruppen.values()];
}

/** SVG-Pfad mit rechtwinkligen Knicken von (sx, Zeile von) nach (tx, Zeile nach). */
export function pfad(p: Pfeil): string {
  const sy = p.von * ZEILE + ZEILE / 2;
  const ty = p.nach * ZEILE + ZEILE / 2;
  if (p.tx >= p.sx + 16) {
    const mx = p.sx + 8;
    return `M${p.sx},${sy} H${mx} V${ty} H${p.tx - 2}`;
  }
  const richtung = ty >= sy ? 1 : -1;
  const zwischen = sy + richtung * (ZEILE / 2);
  return `M${p.sx},${sy} H${p.sx + 8} V${zwischen} H${p.tx - 10} V${ty} H${p.tx - 2}`;
}

/** Monatsgrenzen für die Kopfzeile. */
export function monate(start: string, ende: string): { beginn: string; tage: number }[] {
  const ergebnis: { beginn: string; tage: number }[] = [];
  let d = start;
  while (d <= ende) {
    const [j, m] = d.split("-").map(Number);
    const naechster = m === 12 ? `${j + 1}-01-01` : `${j}-${String(m + 1).padStart(2, "0")}-01`;
    const letzter = naechster > ende ? plusTage(ende, 1) : naechster;
    ergebnis.push({ beginn: d, tage: tageZwischen(d, letzter) });
    d = naechster;
  }
  return ergebnis;
}
