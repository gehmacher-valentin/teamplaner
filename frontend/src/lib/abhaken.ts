/**
 * Abgehakte Aufgaben bleiben kurz sichtbar (Projektliste, „Meine Aufgaben“):
 * Der Server liefert die Zeile nach dem Abhaken im erledigten Zustand ([data-erledigt]). Sie bleibt
 * NACHLAUF_MS stehen und lässt sich so lange mit demselben Haken zurücknehmen (dann ersetzt der Server die
 * Zeile, und der Zeitgeber der alten läuft ins Leere). Danach klappt sie zu, wenn die Liste nur offene
 * Aufgaben zeigt ([data-nur-offen]); jede Zeile hat ihren eigenen Zeitgeber.
 * Wiederkehrende Aufgaben: Die Folgeaufgabe liegt als <template data-folgeaufgabe> in der Zeile und wird
 * erst nach Ablauf eingesetzt (hervorgehoben) – so landet ein schneller zweiter Klick nicht auf ihr.
 */
import htmx from "htmx.org";
import { zaehlerAktualisieren } from "./offenzaehler";

export const NACHLAUF_MS = 5000;
const ZUKLAPPEN_MS = 300;

function ohneBewegung(): boolean {
  return window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false;
}

/** Zeile (bzw. ihren Block ohne weitere Zeilen) zuklappen und entfernen. */
function wegklappen(zeile: HTMLElement) {
  const karte = zeile.closest("[data-zaehlen]");
  const block = zeile.closest<HTMLElement>(".aufgabe-block");
  const ziel = block && block.querySelectorAll("[data-zeile]").length === 1 ? block : zeile;
  const fertig = () => {
    ziel.remove();
    zaehlerAktualisieren(karte);
  };
  if (ohneBewegung()) {
    fertig();
    return;
  }
  ziel.style.height = `${ziel.offsetHeight}px`;
  void ziel.offsetHeight; // Höhe festschreiben, damit der Übergang von hier aus läuft
  ziel.classList.add("zeile-weg");
  ziel.style.height = "0px";
  window.setTimeout(fertig, ZUKLAPPEN_MS);
}

/** Folgeaufgabe aus dem <template> hinter die Zeile bzw. ihren Block setzen. */
function folgeEinsetzen(zeile: HTMLElement, vorlage: HTMLTemplateElement) {
  const block = zeile.closest<HTMLElement>(".aufgabe-block");
  const nach = block && block.firstElementChild === zeile ? block : zeile;
  const html = vorlage.innerHTML;
  vorlage.remove();
  htmx.swap(nach, html, { swapStyle: "afterend", swapDelay: 0, settleDelay: 0 });
  const neu = nach.nextElementSibling;
  const neueZeile = neu?.matches("[data-zeile]") ? neu : neu?.querySelector("[data-zeile]");
  neueZeile?.classList.add("zeile-neu");
}

function ablaufen(zeile: HTMLElement) {
  if (!zeile.isConnected || !zeile.hasAttribute("data-erledigt")) return; // inzwischen ersetzt (rückgängig)
  if (zeile.querySelector(".htmx-request")) {
    // Klick auf den Haken läuft gerade: auf die Antwort warten statt ihr zuvorzukommen
    window.setTimeout(() => ablaufen(zeile), 200);
    return;
  }
  const vorlage = zeile.querySelector<HTMLTemplateElement>("template[data-folgeaufgabe]");
  if (vorlage) folgeEinsetzen(zeile, vorlage);
  if (zeile.closest("[data-nur-offen]")) wegklappen(zeile);
  else zaehlerAktualisieren(zeile.closest("[data-zaehlen]"));
}

/** Für jede neu eingesetzte Zeile (HTMX-Antwort aufs Abhaken bzw. OOB aus der Seitenleiste) aufrufen. */
export function nachAbhaken(element: Node) {
  if (!(element instanceof HTMLElement) || !element.matches("[data-zeile]")) return;
  zaehlerAktualisieren(element.closest("[data-zaehlen]"));
  if (!element.hasAttribute("data-erledigt")) return;
  if (!element.closest("[data-nur-offen]") && !element.querySelector("template[data-folgeaufgabe]")) return;
  window.setTimeout(() => ablaufen(element), NACHLAUF_MS);
}

export function initAbhaken() {
  htmx.onLoad((element) => nachAbhaken(element));
}
