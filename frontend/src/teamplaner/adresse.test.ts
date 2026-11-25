import { describe, expect, it } from "vitest";
import { ohnePaletteVorgabe, paletteAusAdresse } from "./adresse";

describe("Palette aus der Adresse", () => {
  it("liest Projekt und Titel, auch mit Sonderzeichen", () => {
    expect(paletteAusAdresse("?projekt=7&suche=Hallenboden%20Nord%20%26%20S%C3%BCd")).toEqual({
      projekt: 7, suche: "Hallenboden Nord & Süd",
    });
    expect(paletteAusAdresse("?projekt=7")).toEqual({ projekt: 7, suche: "" });
  });

  it("ohne gültiges Projekt nichts", () => {
    for (const abfrage of ["", "?suche=x", "?projekt=abc&suche=x", "?projekt=-3", "?projekt=1.5", "?projekt=0"]) {
      expect(paletteAusAdresse(abfrage), abfrage).toBeNull();
    }
  });

  it("entfernt nur die eigenen Parameter aus der Adresse", () => {
    expect(ohnePaletteVorgabe("http://localhost/teamplaner/?projekt=7&suche=x")).toBe("/teamplaner/");
    expect(ohnePaletteVorgabe("http://localhost/teamplaner/?ansicht=2&projekt=7&suche=x#heute")).toBe("/teamplaner/?ansicht=2#heute");
  });
});
