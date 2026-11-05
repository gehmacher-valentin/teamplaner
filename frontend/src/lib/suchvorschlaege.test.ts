import { describe, expect, it } from "vitest";
import { naechsterIndex } from "./suchvorschlaege";

describe("naechsterIndex", () => {
  it("blättert nach unten bis zum letzten Treffer", () => {
    expect(naechsterIndex(-1, 3, 1)).toBe(0);
    expect(naechsterIndex(1, 3, 1)).toBe(2);
    expect(naechsterIndex(2, 3, 1)).toBe(2);
  });
  it("nach oben zurück ins Eingabefeld", () => {
    expect(naechsterIndex(2, 3, -1)).toBe(1);
    expect(naechsterIndex(0, 3, -1)).toBe(-1);
    expect(naechsterIndex(-1, 3, -1)).toBe(-1);
  });
  it("ohne Treffer nichts gewählt", () => {
    expect(naechsterIndex(-1, 0, 1)).toBe(-1);
  });
});
