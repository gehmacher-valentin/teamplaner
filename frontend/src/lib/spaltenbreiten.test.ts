import { describe, expect, test } from "vitest";
import { breiteAendern, listenbreite, MINDESTBREITE, pxListe, zuruecksetzen } from "./spaltenbreiten";

describe("Spaltenbreiten", () => {
  test("breiter und schmäler ziehen ändert nur die eine Spalte", () => {
    expect(breiteAendern([300, 170, 140], 1, 30)).toEqual([300, 200, 140]);
    expect(breiteAendern([300, 170, 140], 0, -100)).toEqual([200, 170, 140]);
  });

  test("nie schmäler als die Mindestbreite", () => {
    expect(breiteAendern([300, 170, 140], 2, -500)).toEqual([300, 170, MINDESTBREITE]);
    expect(MINDESTBREITE).toBe(48);
  });

  test("Doppelklick setzt nur diese Spalte auf die Standardbreite zurück", () => {
    const standard = [300, 170, 140];
    expect(zuruecksetzen([420, 90, 200], standard, 1)).toEqual([420, 170, 200]);
  });

  test("berechnete Breiten aus getComputedStyle lesen", () => {
    expect(pxListe("412.5px 170px 140px")).toEqual([412.5, 170, 140]);
  });

  test("Mindestbreite der Liste: Spalten, Abstände, Innenabstand", () => {
    expect(listenbreite([300, 170, 140], 12, 32)).toBe(300 + 170 + 140 + 2 * 12 + 32);
  });
});
