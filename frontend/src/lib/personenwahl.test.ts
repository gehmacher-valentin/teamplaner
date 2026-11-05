// @vitest-environment jsdom
import { describe, expect, it } from "vitest";
import { passt, personenwahlEinrichten } from "./personenwahl";

describe("Personenauswahl mit Tippsuche", () => {
  it("findet ohne Akzente und mit mehreren Wörtern", () => {
    expect(passt("Person 01", "pers 1")).toBe(true);
    expect(passt("Jürgen Müller", "mul")).toBe(true);
    expect(passt("Jürgen Müller", "müller jü")).toBe(true);
    expect(passt("Aushilfe Montage (Platzhalter)", "platz")).toBe(true);
    expect(passt("Person 01", "02")).toBe(false);
  });

  it("filtert beim Tippen und setzt das Select samt change-Ereignis", () => {
    document.body.innerHTML = `<form><label>Verantwortlich <select name="v">
      <option value="">Nicht zugewiesen</option><option value="1">Person 01</option>
      <option value="2" selected>Person 02</option><option value="3">Leihkraft Prüfung (Platzhalter)</option>
    </select></label></form>`;
    const select = document.querySelector("select")!;
    const aenderungen: string[] = [];
    document.querySelector("form")!.addEventListener("change", (e) => aenderungen.push((e.target as HTMLElement).tagName));
    personenwahlEinrichten(select);
    const eingabe = document.querySelector<HTMLInputElement>(".personenwahl__eingabe")!;
    expect(eingabe.value).toBe("Person 02");
    expect(eingabe.placeholder).toBe("Nicht zugewiesen");
    expect(eingabe.getAttribute("aria-label")).toBe("Verantwortlich");
    expect(document.querySelector("label")!.control).toBe(eingabe); // Klick auf die Beschriftung fokussiert das Textfeld

    eingabe.dispatchEvent(new Event("focus"));
    eingabe.value = "leih";
    eingabe.dispatchEvent(new Event("input"));
    const optionen = Array.from(document.querySelectorAll(".personenwahl__option")).map((o) => o.textContent);
    expect(optionen).toEqual(["Leihkraft Prüfung (Platzhalter)"]);
    eingabe.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter" }));
    expect(select.value).toBe("3");
    expect(eingabe.value).toBe("Leihkraft Prüfung (Platzhalter)");
    expect(aenderungen).toEqual(["SELECT"]); // nur das Select löst Formular-Aktionen aus

    // Leeren und verlassen: „Nicht zugewiesen“
    eingabe.dispatchEvent(new Event("focus"));
    eingabe.value = "";
    eingabe.dispatchEvent(new Event("input"));
    eingabe.dispatchEvent(new Event("blur"));
    expect(select.value).toBe("");
    expect(eingabe.value).toBe("");
  });
});
