// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { initErwaehnungen, MUSTER } from "./erwaehnungen";

describe("Auslösemuster", () => {
  it("@ am Anfang oder nach Leerraum, auch ohne Suchtext", () => {
    expect("@".match(MUSTER)?.[2]).toBeUndefined();
    expect("Hallo @Pe".match(MUSTER)?.[2]).toBe("Pe");
    expect("Zeile 1\n@Person 05".match(MUSTER)?.[2]).toBe("Person 05"); // Leerzeichen im Namen erlaubt
  });

  it("nicht in E-Mail-Adressen und nicht nach einem zweiten @", () => {
    expect("max@firma".match(MUSTER)).toBeNull();
    expect("@@".match(MUSTER)).toBeNull();
    expect("@ ".match(MUSTER)).toBeNull(); // Leerzeichen direkt nach @
  });

  it("höchstens 31 Zeichen nach dem @, nicht über einen Zeilenumbruch", () => {
    expect(`@${"a".repeat(31)}`.match(MUSTER)).not.toBeNull();
    expect(`@${"a".repeat(32)}`.match(MUSTER)).toBeNull();
    expect("@Pe\nweiter".match(MUSTER)).toBeNull();
  });
});

describe("Vorschläge und verstecktes Feld", () => {
  const personen = [
    { id: 5, name: "Person 05", initialen: "P5", platzhalter: false, foto: null },
    { id: 7, name: "Aushilfe Montage", initialen: "AM", platzhalter: true, foto: null },
  ];
  let abfragen: string[];

  beforeEach(() => {
    vi.useFakeTimers();
    abfragen = [];
    vi.stubGlobal("fetch", vi.fn(async (url: string) => {
      abfragen.push(url);
      return { ok: true, json: async () => ({ personen }) };
    }));
    document.body.innerHTML = `
      <form><div><textarea data-erwaehnung-url="/personen/vorschlaege/"></textarea></div>
      <input type="hidden" name="erwaehnungen" value=""></form>`;
    initErwaehnungen(document);
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  const feld = () => document.querySelector("textarea")!;
  const versteckt = () => document.querySelector<HTMLInputElement>('input[name="erwaehnungen"]')!;
  const liste = () => document.querySelector<HTMLUListElement>("ul.vorschlaege")!;

  async function tippen(text: string) {
    feld().value = text;
    feld().setSelectionRange(text.length, text.length);
    feld().dispatchEvent(new Event("input"));
    await vi.advanceTimersByTimeAsync(150);
  }

  function taste(key: string) {
    feld().dispatchEvent(new KeyboardEvent("keydown", { key, cancelable: true }));
  }

  it("sucht nach kurzer Pause, wählt mit Pfeil und Enter, schreibt die Zuordnung ins Feld", async () => {
    await tippen("Bitte @Au");
    expect(abfragen).toEqual(["/personen/vorschlaege/?q=Au"]);
    expect(liste().hidden).toBe(false);
    expect([...liste().querySelectorAll("li")].map((li) => li.textContent)).toEqual(["P5Person 05", expect.stringMatching(/^AMAushilfe Montage \(/)]);
    taste("ArrowDown");
    expect(liste().querySelectorAll("li")[1].getAttribute("aria-selected")).toBe("true");
    taste("Enter");
    expect(feld().value).toBe("Bitte @Aushilfe Montage ");
    expect(JSON.parse(versteckt().value)).toEqual({ "Aushilfe Montage": 7 });
    expect(liste().hidden).toBe(true);
    // Zweite Erwähnung ergänzt die Zuordnung
    await tippen(`${feld().value}und @Pe`);
    taste("Tab");
    expect(feld().value).toBe("Bitte @Aushilfe Montage und @Person 05 ");
    expect(JSON.parse(versteckt().value)).toEqual({ "Aushilfe Montage": 7, "Person 05": 5 });
  });

  it("nur die letzte Eingabe fragt an; ohne @ schließt die Liste, Escape ebenso", async () => {
    feld().value = "@P";
    feld().dispatchEvent(new Event("input"));
    await tippen("@Pe");
    expect(abfragen).toEqual(["/personen/vorschlaege/?q=Pe"]);
    await tippen("max@firma");
    expect(liste().hidden).toBe(true);
    await tippen("@");
    expect(liste().hidden).toBe(false);
    taste("Escape");
    expect(liste().hidden).toBe(true);
    expect(versteckt().value).toBe("");
  });

  it("richtet jedes Feld nur einmal ein", () => {
    initErwaehnungen(document);
    expect(document.querySelectorAll("ul.vorschlaege")).toHaveLength(1);
  });
});
