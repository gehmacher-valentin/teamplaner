import { describe, expect, it } from "vitest";
import {
  doppelbelegungen,
  kalenderwoche,
  position,
  spuren,
  verschieben,
  zaehlendeTage,
} from "./logik";

// Mo 19.10.2026 … So 01.11.2026, Mo 26.10. Nationalfeiertag; Wochenenden kommen vom Server als frei
const FREI = new Map([["2026-10-24", "Wochenende"], ["2026-10-25", "Wochenende"], ["2026-10-26", "Nationalfeiertag"]]);
const SPALTEN = ["2026-10-19", "2026-10-20", "2026-10-21", "2026-10-22", "2026-10-23", "2026-10-24", "2026-10-25",
  "2026-10-26", "2026-10-27", "2026-10-28", "2026-10-29", "2026-10-30", "2026-10-31", "2026-11-01"];

describe("zaehlendeTage", () => {
  it("überspringt Wochenende und Feiertag bei mehrtägigen Balken", () => {
    expect(zaehlendeTage("2026-10-23", "2026-10-27", FREI)).toEqual(["2026-10-23", "2026-10-27"]);
  });
  it("zählt eintägige Einteilung auf Feiertag und Wochenende", () => {
    expect(zaehlendeTage("2026-10-26", "2026-10-26", FREI)).toEqual(["2026-10-26"]);
    expect(zaehlendeTage("2026-10-24", "2026-10-24", FREI)).toEqual(["2026-10-24"]);
  });
});

describe("doppelbelegungen", () => {
  it("erkennt Überschneidung und Abwesenheit, nicht aber den Feiertag im Balken", () => {
    const e = [
      { person_id: 1, von: "2026-10-23", bis: "2026-10-27" },
      { person_id: 1, von: "2026-10-26", bis: "2026-10-28" },
    ];
    const a = [{ person_id: 1, von: "2026-10-28", bis: "2026-10-28" }];
    expect([...doppelbelegungen(e, a, FREI)].sort()).toEqual(["1:2026-10-27", "1:2026-10-28"]);
  });
});

describe("position", () => {
  it("setzt Balken über das Wochenende zusammenhängend", () => {
    expect(position("2026-10-22", "2026-10-27", SPALTEN)).toEqual({
      start: 3, ende: 8, linksAbgeschnitten: false, rechtsAbgeschnitten: false,
    });
  });
  it("schneidet Balken am Rand ab", () => {
    expect(position("2026-10-14", "2026-10-20", SPALTEN)).toMatchObject({ start: 0, ende: 1, linksAbgeschnitten: true });
    expect(position("2026-11-02", "2026-11-03", SPALTEN)).toBeNull();
    expect(position("2026-10-31", "2026-11-03", SPALTEN)).toMatchObject({ start: 12, ende: 13, rechtsAbgeschnitten: true });
  });
});

describe("spuren", () => {
  it("legt überlappende Balken in eigene Spuren", () => {
    const p = (start: number, ende: number) => ({ position: { start, ende, linksAbgeschnitten: false, rechtsAbgeschnitten: false } });
    const s = spuren([p(0, 2), p(3, 4), p(1, 1), p(2, 5)]);
    expect(s.map((spur) => spur.map((x) => x.position.start))).toEqual([[0, 3], [1, 2]]);
  });
});

describe("Kalendertage", () => {
  it("verschiebt um sichtbare Spalten, auch aufs Wochenende", () => {
    expect(verschieben("2026-10-21", "2026-10-23", 1)).toEqual({ von: "2026-10-22", bis: "2026-10-24" });
    expect(verschieben("2026-10-26", "2026-10-26", -2)).toEqual({ von: "2026-10-24", bis: "2026-10-24" });
  });
  it("berechnet ISO-Kalenderwochen", () => {
    expect(kalenderwoche("2026-10-19")).toBe(43);
    expect(kalenderwoche("2027-01-01")).toBe(53);
    expect(kalenderwoche("2026-01-01")).toBe(1);
  });
});

