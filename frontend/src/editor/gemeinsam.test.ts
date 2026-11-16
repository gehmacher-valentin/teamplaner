import { describe, expect, it } from "vitest";
import * as Y from "yjs";
import { positionNachAenderung, textAngleichen, zuBytes, zuText } from "./gemeinsam";

function zweiDokumente() {
  const a = new Y.Doc();
  const b = new Y.Doc();
  a.on("update", (u: Uint8Array, herkunft: unknown) => { if (herkunft !== "b") Y.applyUpdate(b, u, "a"); });
  b.on("update", (u: Uint8Array, herkunft: unknown) => { if (herkunft !== "a") Y.applyUpdate(a, u, "b"); });
  return [a, b];
}

describe("gemeinsam bearbeiten", () => {
  it("Base64 hin und zurück, auch für große Änderungen", () => {
    const bytes = new Uint8Array(100_000).map((_x, i) => i % 256);
    expect(zuBytes(zuText(bytes))).toEqual(bytes);
  });

  it("Titel ändert nur den geänderten Abschnitt", () => {
    const doc = new Y.Doc();
    const titel = doc.getText("titel");
    textAngleichen(titel, "Prüfplan");
    textAngleichen(titel, "Prüfplan Hebebühne");
    textAngleichen(titel, "Prüfplan Hebebühne");
    expect(titel.toString()).toBe("Prüfplan Hebebühne");
    textAngleichen(titel, "Plan Hebebühne");
    expect(titel.toString()).toBe("Plan Hebebühne");
  });

  it("gleichzeitige Änderungen am Titel gehen beide nicht verloren", () => {
    const [a, b] = zweiDokumente();
    textAngleichen(a.getText("titel"), "Liste");
    // ohne Abgleich dazwischen: a hängt hinten an, b schreibt vorne dazu
    const offline = new Y.Doc();
    Y.applyUpdate(offline, Y.encodeStateAsUpdate(b));
    textAngleichen(a.getText("titel"), "Liste Halle");
    textAngleichen(offline.getText("titel"), "Neue Liste");
    Y.applyUpdate(a, Y.encodeStateAsUpdate(offline));
    expect(a.getText("titel").toString()).toBe("Neue Liste Halle");
    expect(b.getText("titel").toString()).toBe("Neue Liste Halle");
  });

  it("Cursor rückt bei fremden Änderungen davor mit", () => {
    expect(positionNachAenderung(5, [{ insert: "abc" }])).toBe(8);
    expect(positionNachAenderung(5, [{ retain: 6 }, { insert: "abc" }])).toBe(5);
    expect(positionNachAenderung(5, [{ retain: 1 }, { delete: 2 }])).toBe(3);
    expect(positionNachAenderung(2, [{ delete: 5 }])).toBe(0);
  });
});
