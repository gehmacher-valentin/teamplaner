import { describe, expect, it } from "vitest";
import { FIGUREN, naechsteFigur } from "./feiern";

describe("naechsteFigur", () => {
  const namen = FIGUREN.map((f) => f.name);

  it("wählt nie dieselbe Figur wie zuletzt", () => {
    for (const letzte of namen) {
      for (const z of [0, 0.2, 0.5, 0.8, 0.999999]) {
        expect(naechsteFigur(namen, letzte, () => z)).not.toBe(letzte);
      }
    }
  });

  it("erreicht jede andere Figur", () => {
    const gesehen = new Set<string>();
    for (let i = 0; i < 1000; i += 1) gesehen.add(naechsteFigur(namen, "rakete", () => i / 1000));
    expect([...gesehen].sort()).toEqual(namen.filter((n) => n !== "rakete").sort());
  });

  it("ohne vorherige Figur ist jede möglich, auch bei Zufall nahe 1", () => {
    expect(naechsteFigur(namen, null, () => 0)).toBe(namen[0]);
    expect(naechsteFigur(namen, null, () => 0.9999999)).toBe(namen[namen.length - 1]);
  });

  it("eine einzige Figur darf sich wiederholen", () => {
    expect(naechsteFigur(["rakete"], "rakete", () => 0.5)).toBe("rakete");
  });
});

describe("FIGUREN", () => {
  it("enthält die gewünschte Auswahl, jede mit Grafik außer dem Einhorn", () => {
    expect(FIGUREN.map((f) => f.name)).toEqual([
      "einhorn", "rakete", "ufo", "kaenguru", "trex", "flamingo", "otter", "lama", "geist", "partygesicht", "pinata",
    ]);
    for (const f of FIGUREN) expect(Boolean(f.bild), f.name).toBe(f.name !== "einhorn");
  });
});
