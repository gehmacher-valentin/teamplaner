// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { NACHLAUF_MS, nachAbhaken } from "./abhaken";

// htmx selbst läuft nicht in jsdom; abhaken.ts braucht nur swap mit „afterend“
vi.mock("htmx.org", () => ({
  default: {
    swap: (ziel: Element, html: string, { swapStyle }: { swapStyle: string }) => {
      if (swapStyle !== "afterend") throw new Error(`unerwartet: ${swapStyle}`);
      ziel.insertAdjacentHTML("afterend", html);
    },
    onLoad: () => {},
  },
}));

// Nachlauf nach dem Abhaken mit Fake-Timern statt im Browser abzuwarten (E2E 09 prüft den Ablauf einmal echt)
beforeEach(() => vi.useFakeTimers());
afterEach(() => vi.useRealTimers());

function liste(nurOffen: boolean, zeilen: string) {
  document.body.innerHTML = `
    <section id="karte" data-zaehlen ${nurOffen ? "data-nur-offen" : ""}>
      <span data-zaehler>?</span>
      <div data-gruppe><span data-gruppe-zahl>?</span>${zeilen}</div>
      <p data-leer hidden>Keine offenen Aufgaben</p>
    </section>`;
}

const zeile = (id: string) => document.getElementById(id);
const zaehler = () => document.querySelector("[data-zaehler]")!.textContent;

describe("Nachlauf abgehakter Zeilen", () => {
  it("bleibt bis zum Ablauf stehen, klappt dann zu und zählt neu", () => {
    liste(true, `<div id="a" data-zeile data-erledigt>A</div><div id="b" data-zeile>B</div>`);
    nachAbhaken(zeile("a")!);
    expect(zaehler()).toBe("1"); // sofort: erledigte Zeile zählt nicht mehr
    vi.advanceTimersByTime(NACHLAUF_MS - 1);
    expect(zeile("a")).not.toBeNull();
    vi.advanceTimersByTime(1);
    expect(zeile("a")!.classList.contains("zeile-weg")).toBe(true);
    vi.advanceTimersByTime(300);
    expect(zeile("a")).toBeNull();
    expect(zaehler()).toBe("1");
  });

  it("die letzte Zeile weg: Gruppe entfernt, Leer-Meldung sichtbar", () => {
    liste(true, `<div id="a" data-zeile data-erledigt>A</div>`);
    nachAbhaken(zeile("a")!);
    vi.advanceTimersByTime(NACHLAUF_MS + 300);
    expect(document.querySelector("[data-gruppe]")).toBeNull();
    expect(document.querySelector<HTMLElement>("[data-leer]")!.hidden).toBe(false);
  });

  it("rückgängig gemacht (Zeile vom Server ersetzt): der alte Zeitgeber läuft ins Leere", () => {
    liste(true, `<div id="a" data-zeile data-erledigt>A</div>`);
    nachAbhaken(zeile("a")!);
    zeile("a")!.outerHTML = `<div id="a" data-zeile>A wieder offen</div>`;
    nachAbhaken(zeile("a")!);
    vi.advanceTimersByTime(NACHLAUF_MS * 2);
    expect(zeile("a")!.textContent).toBe("A wieder offen");
    expect(zaehler()).toBe("1");
  });

  it("wartet auf eine laufende HTMX-Anfrage in der Zeile statt ihr zuvorzukommen", () => {
    liste(true, `<div id="a" data-zeile data-erledigt><button class="htmx-request">✓</button></div>`);
    nachAbhaken(zeile("a")!);
    vi.advanceTimersByTime(NACHLAUF_MS + 1000);
    expect(zeile("a")!.classList.contains("zeile-weg")).toBe(false);
    zeile("a")!.querySelector("button")!.classList.remove("htmx-request");
    vi.advanceTimersByTime(200 + 300);
    expect(zeile("a")).toBeNull();
  });

  it("Liste mit allen Aufgaben: erledigte Zeile bleibt, ohne Folgeaufgabe kein Zeitgeber", () => {
    liste(false, `<div id="a" data-zeile data-erledigt>A</div>`);
    nachAbhaken(zeile("a")!);
    expect(vi.getTimerCount()).toBe(0);
    vi.advanceTimersByTime(NACHLAUF_MS * 2);
    expect(zeile("a")).not.toBeNull();
  });

  it("Folgeaufgabe erst nach Ablauf, hinter der Zeile und hervorgehoben", () => {
    liste(false, `<div id="a" data-zeile data-erledigt>A<template data-folgeaufgabe><div id="neu" data-zeile>A nächste Woche</div></template></div>`);
    nachAbhaken(zeile("a")!);
    vi.advanceTimersByTime(NACHLAUF_MS - 1);
    expect(zeile("neu")).toBeNull();
    vi.advanceTimersByTime(1);
    const neu = zeile("neu")!;
    expect(neu.previousElementSibling!.id).toBe("a");
    expect(neu.classList.contains("zeile-neu")).toBe(true);
    expect(zeile("a")!.querySelector("template")).toBeNull();
    expect(zaehler()).toBe("1");
  });

  it("offene Zeilen und fremde Elemente starten keinen Zeitgeber", () => {
    liste(true, `<div id="a" data-zeile>A</div><div id="x">kein Eintrag</div>`);
    nachAbhaken(zeile("a")!);
    nachAbhaken(zeile("x")!);
    nachAbhaken(document.createTextNode("Text"));
    expect(vi.getTimerCount()).toBe(0);
  });
});
