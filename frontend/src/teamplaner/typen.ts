// Datenformate der Teamplaner-API (planung/raster.py, planung/api.py)

export type Recht = "sehen" | "bearbeiten";

export interface Ansicht {
  id: string;
  name: string;
  recht: Recht;
  filter: { gewerke?: number[]; projekte?: number[]; tags?: number[]; bereiche?: number[]; wochen?: number };
}

export interface Tag {
  datum: string;
  wochentag: number;
  kw: number;
  frei: string | null;
  /** Freitext der Info-Zeile, leer = nichts eingetragen */
  info: string;
  /** Tagesfreigabe (Wert aus freigabe_stufen), leer = keine Freigabe */
  freigabe: string;
  /** Wer die Tagesfreigabe zuletzt gesetzt hat (Anzeigename), leer bei keiner Freigabe */
  freigabe_von: string;
}

/** Tagesfreigabe eines Tags, wie sie angezeigt wird */
export interface FreigabeTag {
  stufe: string;
  /** Name der Stufe, leer = keine Freigabe */
  name: string;
  von: string;
}

export interface Person {
  id: number;
  name: string;
  initialen: string;
  foto: string | null;
  bereich_id: number;
  gewerke: string[];
  gewerk_ids: number[];
  platzhalter: boolean;
  archiviert: boolean;
  ich: boolean;
  einteilbar: boolean;
  /** false bei Systemkonten: nur bestehende Einträge, keine neuen */
  auswaehlbar: boolean;
}

export interface Einteilung {
  id: number;
  aufgabe_id: number;
  person_id: number;
  von: string;
  bis: string;
  version: number;
}

export interface Abwesenheit {
  id: number;
  person_id: number;
  von: string;
  bis: string;
  version: number;
}

export interface Aufgabe {
  id: number;
  titel: string;
  /** Pfad der Hauptaufgaben („A › B“), wenn dies eine Unteraufgabe ist */
  eltern: string | null;
  projekt_id: number;
  gewerk: string;
  gewerk_id: number | null;
  status: string;
  erledigt: boolean;
  schaetzung: number | null;
  eingeteilt: number;
  personen: number;
  faellig_am: string | null;
  /** Anzahl Dateianhänge (Büroklammer auf der Karte) */
  anhaenge: number;
  url: string;
}

export interface Projekt {
  id: number;
  name: string;
  farbe: string;
  tags: number[];
}

export interface Raster {
  von: string;
  bis: string;
  heute: string;
  /** Info-Zeile bearbeiten (wer im Teamplaner planen darf) */
  info_bearbeitbar: boolean;
  /** Zeile „Tagesfreigabe“ anzeigen (globale Einstellung) */
  freigabe_zeile: boolean;
  /** Vom Admin gewählter Name der Zeile */
  freigabe_name: string;
  freigabe_stufen: { wert: string; name: string }[];
  tage: Tag[];
  bereiche: { id: number; name: string }[];
  personen: Person[];
  einteilungen: Einteilung[];
  abwesenheiten: Abwesenheit[];
  aufgaben: Record<string, Aufgabe>;
  projekte: Record<string, Projekt>;
  doppelbelegungen: { person_id: number; datum: string }[];
}

export interface Optionen {
  ansichten: Ansicht[];
  darf_planen: boolean;
  projekte: Projekt[];
  tags: { id: number; name: string }[];
  gewerke: { id: number; name: string }[];
  bereiche: { id: number; name: string }[];
}

export interface PaletteDaten {
  aufgaben: Aufgabe[];
  projekte: Record<string, Projekt>;
}

/** Ein Balken im Raster – Einteilung oder Abwesenheit. */
export type Eintrag =
  | ({ art: "einteilung" } & Einteilung)
  | ({ art: "abwesenheit" } & Abwesenheit);
