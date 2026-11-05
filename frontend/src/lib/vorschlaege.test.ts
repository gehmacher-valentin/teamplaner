// @vitest-environment jsdom
import { describe, expect, it } from "vitest";
import { vorschlaegeEinrichten, vorschlaegeFiltern } from "./vorschlaege";

const LIEFERANTEN = ["Ärztebedarf", "Baumarkt Nord", "Conrad Electronic", "Würth"];

describe("Lieferant mit Vorschlägen", () => {
  it("filtert ohne Groß-/Kleinschreibung und Akzente, Treffer irgendwo im Namen", () => {
    expect(vorschlaegeFiltern(LIEFERANTEN, "")).toEqual(LIEFERANTEN);
    expect(vorschlaegeFiltern(LIEFERANTEN, "CONRAD")).toEqual(["Conrad Electronic"]);
    expect(vorschlaegeFiltern(LIEFERANTEN, "tron")).toEqual(["Conrad Electronic"]);
    expect(vorschlaegeFiltern(LIEFERANTEN, "arzte")).toEqual(["Ärztebedarf"]);
    expect(vorschlaegeFiltern(LIEFERANTEN, "wurth")).toEqual(["Würth"]);
    expect(vorschlaegeFiltern(LIEFERANTEN, "nord bau")).toEqual(["Baumarkt Nord"]);
    expect(vorschlaegeFiltern(LIEFERANTEN, "xyz")).toEqual([]);
  });

  function aufbauen() {
    document.body.innerHTML = `<form>
      <textarea name="lieferant" aria-label="Lieferant" data-inline data-vorschlaege="quelle"></textarea>
      <datalist id="quelle">${LIEFERANTEN.map((l) => `<option value="${l}"></option>`).join("")}</datalist>
    </form>`;
    const feld = document.querySelector("textarea")!;
    const aenderungen: string[] = [];
    document.querySelector("form")!.addEventListener("change", () => aenderungen.push(feld.value));
    vorschlaegeEinrichten(feld);
    const liste = document.querySelector<HTMLUListElement>(".vorschlaege__liste")!;
    const sichtbar = () => Array.from(liste.querySelectorAll("li"), (li) => li.textContent);
    return { feld, liste, aenderungen, sichtbar };
  }

  function tippen(feld: HTMLTextAreaElement, text: string) {
    feld.value = text;
    feld.dispatchEvent(new Event("input", { bubbles: true }));
  }

  it("zeigt beim Fokus alle, filtert beim Tippen und wählt per Pfeiltaste und Enter", () => {
    const { feld, liste, aenderungen, sichtbar } = aufbauen();
    feld.dispatchEvent(new Event("focus"));
    expect(liste.hidden).toBe(false);
    expect(sichtbar()).toEqual(LIEFERANTEN);
    expect(feld.getAttribute("aria-expanded")).toBe("true");

    tippen(feld, "r");
    expect(sichtbar()).toEqual(["Ärztebedarf", "Baumarkt Nord", "Conrad Electronic", "Würth"]);
    tippen(feld, "ar");
    expect(sichtbar()).toEqual(["Ärztebedarf", "Baumarkt Nord"]);

    feld.dispatchEvent(new KeyboardEvent("keydown", { key: "ArrowDown" }));
    feld.dispatchEvent(new KeyboardEvent("keydown", { key: "ArrowDown" }));
    const enter = new KeyboardEvent("keydown", { key: "Enter", cancelable: true, bubbles: true });
    feld.dispatchEvent(enter);
    expect(enter.defaultPrevented).toBe(true);
    expect(feld.value).toBe("Baumarkt Nord");
    expect(aenderungen).toEqual(["Baumarkt Nord"]);
    expect(liste.hidden).toBe(true);
  });

  it("lässt freien Text zu: ohne Auswahl gehört Enter dem Feld, ohne Treffer keine Liste", () => {
    const { feld, liste, aenderungen } = aufbauen();
    feld.dispatchEvent(new Event("focus"));
    tippen(feld, "Neuer Lieferant");
    expect(liste.hidden).toBe(true);
    const enter = new KeyboardEvent("keydown", { key: "Enter", cancelable: true, bubbles: true });
    feld.dispatchEvent(enter);
    expect(enter.defaultPrevented).toBe(false); // lib/inline.ts speichert dann wie gewohnt
    expect(feld.value).toBe("Neuer Lieferant");
    expect(aenderungen).toEqual([]);
  });

  it("Klick wählt, Escape schließt zuerst nur die Liste", () => {
    const { feld, liste, aenderungen } = aufbauen();
    feld.value = "alt";
    feld.dispatchEvent(new Event("focus"));
    const esc = new KeyboardEvent("keydown", { key: "Escape", cancelable: true, bubbles: true });
    feld.dispatchEvent(esc);
    expect(esc.defaultPrevented).toBe(true);
    expect(liste.hidden).toBe(true);
    expect(feld.value).toBe("alt");

    feld.dispatchEvent(new Event("click"));
    liste.querySelectorAll("li")[1].dispatchEvent(new MouseEvent("click", { bubbles: true }));
    expect(feld.value).toBe("Baumarkt Nord");
    expect(aenderungen).toEqual(["Baumarkt Nord"]);
  });

  it("liest die Vorschläge bei jedem Öffnen neu (nach einer HTMX-Aktualisierung)", () => {
    const { feld, sichtbar } = aufbauen();
    const quelle = document.getElementById("quelle")!;
    quelle.innerHTML = `<option value="Neu GmbH"></option>`;
    feld.dispatchEvent(new Event("focus"));
    expect(sichtbar()).toEqual(["Neu GmbH"]);
  });
});
