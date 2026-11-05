// Datenformate der Gantt-API (gantt/daten.py)
import type { Recht } from "../teamplaner/typen";

export interface GProjekt {
  id: number;
  name: string;
  farbe: string;
  archiviert: boolean;
  beginn: string | null;
  ende: string | null;
  /** Zeitraum der geplanten Aufgabentermine – reicht er über Beginn/Ende hinaus: Überzug */
  plan_von: string | null;
  plan_bis: string | null;
  ist_von: string | null;
  ist_bis: string | null;
  aufgaben: number[];
  url: string;
}

export interface GAufgabe {
  id: number;
  projekt_id: number;
  titel: string;
  /** ID der Hauptaufgabe, wenn dies eine Unteraufgabe ist */
  eltern: number | null;
  /** Unteraufgaben (erste Ebene) in dieser Ansicht – tiefere Ebenen zeigt das Gantt-Diagramm nicht */
  kinder: number[];
  /** Termine ergeben sich aus den Unteraufgaben: nur als Ganzes verschiebbar */
  sammel: boolean;
  abschnitt: string;
  beginn: string | null;
  ende: string | null;
  ist_von: string | null;
  ist_bis: string | null;
  erledigt: boolean;
  status: string;
  status_farbe: string;
  version: number;
  extern: boolean;
  url: string;
}

export interface GAbhaengigkeit {
  id: number;
  vorher: number;
  nachher: number;
  verletzt: boolean;
}

export interface GDaten {
  ansicht: { id: number; name: string; recht: Recht };
  heute: string;
  von: string;
  bis: string;
  frei: Record<string, string>;
  projekte: GProjekt[];
  externe_projekte: Record<string, { id: number; name: string; farbe: string }>;
  aufgaben: Record<string, GAufgabe>;
  abhaengigkeiten: GAbhaengigkeit[];
}

export interface GOptionen {
  ansichten: { id: number; name: string; recht: Recht }[];
  darf_verwalten: boolean;
  projekte: { id: number; name: string; farbe: string }[];
  /** Persönliche Einstellung am Konto */
  unteraufgaben_offen: boolean;
}

/** Eine sichtbare Zeile im Diagramm. */
export type Zeile =
  | { art: "projekt"; projekt: GProjekt; zu: boolean }
  | { art: "aufgabe"; aufgabe: GAufgabe; zu: boolean }
  | { art: "extern" };
