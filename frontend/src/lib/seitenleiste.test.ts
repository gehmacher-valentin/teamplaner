import { describe, expect, it } from "vitest";
import { adresseMit, aufgabeInAdresse, breiteBegrenzen, HOECHSTBREITE, klickAbfangen, MINDESTBREITE } from "./seitenleiste";

const klick = { button: 0, ctrlKey: false, metaKey: false, shiftKey: false, altKey: false };

describe("Breite der Seitenleiste", () => {
  it("bleibt zwischen Mindest- und Höchstbreite", () => {
    expect(breiteBegrenzen(100, 2000)).toBe(MINDESTBREITE);
    expect(breiteBegrenzen(520.4, 2000)).toBe(520);
    expect(breiteBegrenzen(5000, 2000)).toBe(HOECHSTBREITE);
  });

  it("lässt der Liste daneben Platz", () => {
    expect(breiteBegrenzen(800, 1000)).toBe(700);
    expect(breiteBegrenzen(800, 500)).toBe(MINDESTBREITE);
  });
});

describe("Klick auf eine Aufgabe", () => {
  it("wird im breiten Fenster abgefangen", () => {
    expect(klickAbfangen(klick, true)).toBe(true);
  });

  it("bleibt unterhalb der Umbruchbreite ein normaler Link", () => {
    expect(klickAbfangen(klick, false)).toBe(false);
  });

  it.each(["ctrlKey", "metaKey", "shiftKey", "altKey"])("mit %s öffnet die Detailseite im neuen Tab", (taste) => {
    expect(klickAbfangen({ ...klick, [taste]: true }, true)).toBe(false);
  });

  it("mittlere Maustaste bleibt ein normaler Link", () => {
    expect(klickAbfangen({ ...klick, button: 1 }, true)).toBe(false);
  });
});

describe("Adresse", () => {
  it("behält die Filter", () => {
    const mit = adresseMit("https://x.test/projekte/1/?status=alle&q=Aufzug", "7");
    expect(mit).toBe("/projekte/1/?status=alle&q=Aufzug&aufgabe=7");
    expect(aufgabeInAdresse(mit.split("?")[1])).toBe("7");
    expect(adresseMit(`https://x.test${mit}`, null)).toBe("/projekte/1/?status=alle&q=Aufzug");
  });

  it("tauscht die Aufgabe, statt sie zu wiederholen", () => {
    expect(adresseMit("https://x.test/projekte/1/?aufgabe=7", "8")).toBe("/projekte/1/?aufgabe=8");
  });

  it("ohne Aufgabe ist nichts offen", () => {
    expect(aufgabeInAdresse("?status=alle")).toBeNull();
    expect(aufgabeInAdresse("?aufgabe=")).toBeNull();
  });
});
