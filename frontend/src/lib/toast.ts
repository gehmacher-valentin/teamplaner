/**
 * Rückmeldungen als Toast: schweben unten rechts über dem Inhalt (am Handy unten über die
 * ganze Breite), damit nichts springt. Verschwinden nach einigen Sekunden, halten bei Maus oder
 * Fokus an, lassen sich mit × schließen. Fehler bleiben stehen, bis man sie schließt.
 *
 * Quellen: toast() aus TypeScript (Teamplaner, Gantt), Django-Meldungen (base.html rendert sie in
 * #toasts, hier bekommen sie Zeitgeber und ×) und HTMX-Antworten (Ereignis „toasts“ aus dem
 * Header HX-Trigger, gesetzt von kern.middleware.HtmxMeldungenMiddleware).
 */
import { t } from "./texte";

export type ToastArt = "erfolg" | "info" | "fehler";

export interface ToastOptionen {
  art?: ToastArt;
  /** Millisekunden bis zum Ausblenden; 0 = bleibt stehen */
  dauer?: number;
  aktion?: { text: string; ausfuehren: () => void };
}

const SYMBOLE: Record<ToastArt, string> = {
  erfolg: '<path d="M5 12l5 5L20 7"/>',
  info: '<circle cx="12" cy="12" r="9"/><path d="M12 11v5M12 8h.01"/>',
  fehler: '<path d="M12 3l9.5 17h-19z"/><path d="M12 10v4M12 17h.01"/>',
};

function behaelter(): HTMLElement {
  let el = document.getElementById("toasts");
  if (!el) {
    el = document.createElement("div");
    el.id = "toasts";
    el.className = "toasts";
    el.setAttribute("aria-live", "polite");
    document.body.append(el);
  }
  return el;
}

/** Zeitgeber, Pause bei Maus/Fokus und Schließen für ein vorhandenes Toast-Element. */
function einrichten(el: HTMLElement, dauer: number) {
  let rest = dauer;
  let start = 0;
  let zeitgeber: number | undefined;
  const weg = () => {
    window.clearTimeout(zeitgeber);
    el.classList.add("toast--weg");
    const entfernen = () => el.remove();
    el.addEventListener("animationend", entfernen, { once: true });
    window.setTimeout(entfernen, 400); // ohne Animation („Bewegung reduzieren“)
  };
  const laufen = () => {
    if (!rest) return;
    start = Date.now();
    zeitgeber = window.setTimeout(weg, rest);
  };
  const anhalten = () => {
    if (!zeitgeber) return;
    window.clearTimeout(zeitgeber);
    zeitgeber = undefined;
    rest = Math.max(1500, rest - (Date.now() - start));
  };
  el.addEventListener("mouseenter", anhalten);
  el.addEventListener("focusin", anhalten);
  el.addEventListener("mouseleave", () => { if (!el.contains(document.activeElement)) laufen(); });
  el.addEventListener("focusout", (e) => { if (!el.contains(e.relatedTarget as Node | null) && !el.matches(":hover")) laufen(); });
  el.querySelector<HTMLButtonElement>(".toast__zu")?.addEventListener("click", weg);
  el.querySelector<HTMLButtonElement>(".toast__aktion")?.addEventListener("click", weg);
  laufen();
  return weg;
}

function standardDauer(art: ToastArt, aktion: boolean) {
  return art === "fehler" ? 0 : aktion ? 8000 : 6000;
}

/** Zeigt einen Toast; gibt eine Funktion zum Schließen zurück. */
export function toast(text: string, { art = "erfolg", dauer, aktion }: ToastOptionen = {}): () => void {
  const el = document.createElement("div");
  el.className = `toast toast--${art}`;
  el.setAttribute("role", art === "fehler" ? "alert" : "status");
  el.innerHTML = `<svg class="toast__symbol" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor"
    stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${SYMBOLE[art]}</svg>
    <span class="toast__text"></span>`;
  el.querySelector(".toast__text")!.textContent = text;
  if (aktion) {
    const knopf = document.createElement("button");
    knopf.type = "button";
    knopf.className = "toast__aktion";
    knopf.textContent = aktion.text;
    knopf.addEventListener("click", aktion.ausfuehren);
    el.append(knopf);
  }
  const zu = document.createElement("button");
  zu.type = "button";
  zu.className = "toast__zu";
  zu.setAttribute("aria-label", t("schliessen"));
  zu.innerHTML = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" aria-hidden="true"><path d="M6 6l12 12M18 6L6 18"/></svg>';
  el.append(zu);
  behaelter().append(el);
  return einrichten(el, dauer ?? standardDauer(art, !!aktion));
}

/** Django-Meldungen der Seite (in #toasts gerendert) und Toasts aus HTMX-Antworten. */
export function initToasts() {
  document.querySelectorAll<HTMLElement>("#toasts .toast").forEach((el) => {
    einrichten(el, standardDauer(el.classList.contains("toast--fehler") ? "fehler" : "erfolg", false));
  });
  document.body.addEventListener("toasts", (event) => {
    const liste = (event as CustomEvent).detail?.value ?? (event as CustomEvent).detail;
    for (const m of Array.isArray(liste) ? liste : []) toast(String(m.text), { art: m.art });
  });
}
