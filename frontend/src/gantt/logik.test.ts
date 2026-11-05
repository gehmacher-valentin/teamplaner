import { describe, expect, it } from "vitest";
import { balken, monate, pfad, pfeile, projektZeitraum, tageZwischen, x, ZEILE, zeilen } from "./logik";
import type { GDaten } from "./typen";

const aufgabe = (id: number, projekt_id: number, beginn: string | null, ende: string | null, extern = false,
  eltern: number | null = null, kinder: number[] = []) => ({
  id, projekt_id, titel: `A${id}`, eltern, kinder, sammel: kinder.length > 0, abschnitt: "", beginn, ende,
  ist_von: null, ist_bis: null, erledigt: false, status: "Offen", status_farbe: "grau", version: 1, extern, url: "",
});
const projekt = (id: number, beginn: string, ende: string, aufgaben: number[]) => ({
  id, name: `P${id}`, farbe: "blau", archiviert: false, beginn, ende, plan_von: null, plan_bis: null,
  ist_von: null, ist_bis: null, aufgaben, url: "",
});

const daten: GDaten = {
  ansicht: { id: 1, name: "Test", recht: "bearbeiten" },
  heute: "2026-10-22", von: "2026-10-01", bis: "2026-12-31", frei: {},
  projekte: [
    projekt(1, "2026-10-05", "2026-10-30", [10, 11]),
    projekt(2, "2026-11-02", "2026-11-20", [20]),
  ],
  externe_projekte: {},
  aufgaben: {
    10: aufgabe(10, 1, "2026-10-05", "2026-10-09"),
    11: aufgabe(11, 1, null, "2026-10-16"),
    20: aufgabe(20, 2, "2026-11-02", "2026-11-06"),
  },
  abhaengigkeiten: [
    { id: 1, vorher: 10, nachher: 20, verletzt: false },
    { id: 2, vorher: 11, nachher: 20, verletzt: true },
    { id: 3, vorher: 10, nachher: 11, verletzt: false },
  ],
};

describe("Zeitachse", () => {
  it("rechnet Tage und Balken inklusive Endtag", () => {
    expect(tageZwischen("2026-10-01", "2026-10-05")).toBe(4);
    expect(x("2026-10-03", "2026-10-01", 10)).toBe(20);
    expect(balken("2026-10-05", "2026-10-09", "2026-10-01", 10)).toEqual({ links: 40, breite: 50 });
  });
  it("teilt Monate korrekt auf", () => {
    expect(monate("2026-10-20", "2026-12-05").map((m) => m.tage)).toEqual([12, 30, 5]);
  });
});

describe("Zeilen und Pfeile", () => {
  it("klappt Projekte ein", () => {
    expect(zeilen(daten, new Set(), true)).toHaveLength(5);
    expect(zeilen(daten, new Set([1]), true).map((z) => z.art)).toEqual(["projekt", "projekt", "aufgabe"]);
  });
  it("fasst Abhängigkeiten eingeklappter Projekte zusammen und lässt interne weg", () => {
    const offen = pfeile(daten, zeilen(daten, new Set(), true), daten.von, 10);
    expect(offen).toHaveLength(3);
    const zu = pfeile(daten, zeilen(daten, new Set([1]), true), daten.von, 10);
    expect(zu).toHaveLength(1); // 10→20 und 11→20 zusammengefasst, 10→11 entfällt
    expect(zu[0].verletzt).toBe(true);
    expect(zu[0].abhaengigkeiten).toHaveLength(2);
  });
  it("zeichnet rechtwinklige Pfade", () => {
    const d = pfad({ schluessel: "x", von: 0, nach: 2, sx: 50, tx: 200, verletzt: false, abhaengigkeiten: [] });
    expect(d).toBe(`M50,${ZEILE / 2} H58 V${2 * ZEILE + ZEILE / 2} H198`);
  });
});

describe("Unteraufgaben", () => {
  const mitUnter: GDaten = {
    ...daten,
    projekte: [projekt(1, "2026-10-05", "2026-10-30", [10, 12, 13]), projekt(2, "2026-11-02", "2026-11-20", [20])],
    aufgaben: {
      10: aufgabe(10, 1, "2026-10-05", "2026-10-16", false, null, [12, 13]),
      12: aufgabe(12, 1, "2026-10-05", "2026-10-09", false, 10),
      13: aufgabe(13, 1, "2026-10-12", "2026-10-16", false, 10),
      20: aufgabe(20, 2, "2026-11-02", "2026-11-06"),
    },
    abhaengigkeiten: [{ id: 1, vorher: 13, nachher: 20, verletzt: false }],
  };
  it("sind eingeklappt, bis die Hauptaufgabe aufgeklappt wird", () => {
    const zu = zeilen(mitUnter, new Set(), true, () => false);
    expect(zu.filter((z) => z.art === "aufgabe").map((z) => z.art === "aufgabe" && z.aufgabe.id)).toEqual([10, 20]);
    expect(zu[1]).toMatchObject({ art: "aufgabe", zu: true });
    const auf = zeilen(mitUnter, new Set(), true, (id) => id === 10);
    expect(auf.filter((z) => z.art === "aufgabe")).toHaveLength(4);
  });
  it("Pfeile eingeklappter Unteraufgaben beginnen an der Hauptaufgabe", () => {
    const liste = zeilen(mitUnter, new Set(), true, () => false);
    const [p] = pfeile(mitUnter, liste, mitUnter.von, 10);
    expect(p.von).toBe(1); // Zeile der Hauptaufgabe 10
    expect(p.sx).toBe(x("2026-10-16", mitUnter.von, 10) + 10);
  });
});

describe("Projektzeitraum", () => {
  it("wächst mit den Aufgaben und markiert den Überzug", () => {
    const z = projektZeitraum({ beginn: "2026-10-05", ende: "2026-10-30", plan_von: "2026-10-01", plan_bis: "2026-11-04" });
    expect(z).toEqual({
      von: "2026-10-01", bis: "2026-11-04",
      vorne: { von: "2026-10-01", bis: "2026-10-04" }, hinten: { von: "2026-10-31", bis: "2026-11-04" },
    });
  });
  it("ohne Überzug oder ohne eingestellten Zeitraum", () => {
    expect(projektZeitraum({ beginn: "2026-10-05", ende: "2026-10-30", plan_von: "2026-10-06", plan_bis: "2026-10-20" }))
      .toMatchObject({ von: "2026-10-05", bis: "2026-10-30", vorne: null, hinten: null });
    expect(projektZeitraum({ beginn: null, ende: null, plan_von: "2026-10-06", plan_bis: "2026-10-20" }))
      .toMatchObject({ von: "2026-10-06", bis: "2026-10-20", vorne: null, hinten: null });
  });
});
