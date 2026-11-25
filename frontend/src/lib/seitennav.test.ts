import { describe, expect, it } from "vitest";
import { raender, sichtbarePosition } from "./seitennav";

describe("raender", () => {
  it("passt alles hinein: kein Überlauf, keine Schatten", () => {
    expect(raender(0, 300, 300)).toEqual({ ueberlauf: false, mehrOben: false, mehrUnten: false });
  });
  it("oben: nur unten liegen weitere Einträge", () => {
    expect(raender(0, 900, 300)).toEqual({ ueberlauf: true, mehrOben: false, mehrUnten: true });
  });
  it("in der Mitte: beide Ränder", () => {
    expect(raender(200, 900, 300)).toEqual({ ueberlauf: true, mehrOben: true, mehrUnten: true });
  });
  it("ganz unten, auch mit gerundetem scrollTop", () => {
    expect(raender(599.5, 900, 300)).toEqual({ ueberlauf: true, mehrOben: true, mehrUnten: false });
  });
});

describe("sichtbarePosition", () => {
  const liste = { top: 100, bottom: 400 };
  it("sichtbarer Eintrag: Position bleibt", () => {
    expect(sichtbarePosition(50, liste, { top: 200, bottom: 236 })).toBe(50);
  });
  it("Eintrag unterhalb: so weit, dass er mit Abstand unten steht", () => {
    expect(sichtbarePosition(0, liste, { top: 800, bottom: 836 })).toBe(836 - 400 + 12);
  });
  it("Eintrag oberhalb: so weit zurück, dass er mit Abstand oben steht", () => {
    expect(sichtbarePosition(500, liste, { top: 40, bottom: 76 })).toBe(500 - (112 - 40));
  });
  it("Eintrag halb unter dem Schatten am Rand zählt als verdeckt", () => {
    expect(sichtbarePosition(0, liste, { top: 370, bottom: 395 })).toBe(7);
  });
});
