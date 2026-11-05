/**
 * Aufgabendetail als Seitenleiste neben der Projektliste. Die Links auf Aufgaben sind normale
 * Links (a[data-aufgabe-link]); nur ein einfacher Klick im breiten Fenster öffnet die Seitenleiste,
 * alles andere (neuer Tab, schmales Fenster) führt wie gewohnt zur Detailseite.
 *
 * Die Adresse trägt ?aufgabe=<id>, Filter bleiben daneben stehen. Zurück und Vor tauschen nur den
 * Inhalt der Seitenleiste; was HTMX in den Verlauf legt (Filter), lädt die Seite vom Server
 * (hx-history="false"), weil Editor und Tippsuche einen Abzug der Seite nicht überstehen.
 *
 * Ein Wechsel wartet auf laufende Speicheranfragen: deren Antwort setzt Version und Kopf per ID und
 * träfe sonst die nächste Aufgabe. Die Breite gilt bis zum Neuladen, nichts wird gespeichert.
 */

export const UMBRUCH = 1100; // wie in app.css
export const MINDESTBREITE = 380;
export const HOECHSTBREITE = 900;
const LISTE_MINDESTENS = 300;

/** Breite beim Ziehen: nie schmäler als die Mindestbreite, die Liste daneben behält ihren Platz. */
export function breiteBegrenzen(breite: number, rasterbreite: number): number {
  const hoechst = Math.max(MINDESTBREITE, Math.min(HOECHSTBREITE, rasterbreite - LISTE_MINDESTENS));
  return Math.min(hoechst, Math.max(MINDESTBREITE, Math.round(breite)));
}

type Klick = Pick<MouseEvent, "button" | "ctrlKey" | "metaKey" | "shiftKey" | "altKey">;

/** Nur ein einfacher Klick im breiten Fenster; Strg/Cmd-Klick und Co. bleiben normale Links. */
export function klickAbfangen(klick: Klick, breit: boolean): boolean {
  return breit && klick.button === 0 && !klick.ctrlKey && !klick.metaKey && !klick.shiftKey && !klick.altKey;
}

export function aufgabeInAdresse(suche: string): string | null {
  return new URLSearchParams(suche).get("aufgabe") || null;
}

/** Aktuelle Adresse mit oder ohne Aufgabe; alle anderen Angaben (Filter) bleiben. */
export function adresseMit(adresse: string, aufgabe: string | null): string {
  const url = new URL(adresse);
  if (aufgabe) url.searchParams.set("aufgabe", aufgabe);
  else url.searchParams.delete("aufgabe");
  return url.pathname + url.search;
}

let offen: string | null = null; // Aufgabe, die offen ist oder gerade geladen wird
let breite: number | null = null;
let laufend = 0;
let danach: (() => void) | null = null;
let beobachter: ResizeObserver | null = null;

const leiste = () => document.getElementById("seitenleiste");
const platz = () => document.getElementById("seitenleiste-platz");
const raster = () => document.querySelector<HTMLElement>(".projekt-raster");
const istBreit = () => window.matchMedia(`(min-width: ${UMBRUCH}px)`).matches;
const detailAdresse = (id: string) => leiste()!.dataset.url!.replace("/0/", `/${id}/`);

function wennGespeichert(aktion: () => void) {
  danach = aktion;
  weiter();
}

function weiter() {
  if (laufend > 0 || !danach) return;
  const aktion = danach;
  danach = null;
  aktion();
}

function laden(id: string, nachOben: boolean) {
  wennGespeichert(() => {
    const ziel = platz();
    if (!ziel || offen !== id) return;
    window.htmx
      .ajax("get", `${detailAdresse(id)}?seitenleiste=1`, { source: ziel, target: ziel, swap: "innerHTML" })
      .then(() => {
        if (nachOben) ziel.scrollTop = 0;
      })
      .catch(() => undefined); // Fehler meldet schon der Toast
  });
}

function oeffnen(id: string, adresse: boolean) {
  if (adresse) history.pushState({ seitenleiste: true }, "", adresseMit(location.href, id));
  offen = id;
  seitenleisteAbgleichen();
  laden(id, true);
}

function schliessen(adresse: "neu" | "ersetzen" | "keine") {
  const ziel = platz();
  if (document.activeElement instanceof HTMLElement && ziel?.contains(document.activeElement)) document.activeElement.blur();
  const id = offen;
  offen = null;
  if (adresse === "neu") history.pushState({ seitenleiste: true }, "", adresseMit(location.href, null));
  if (adresse === "ersetzen") history.replaceState({ seitenleiste: true }, "", adresseMit(location.href, null));
  seitenleisteAbgleichen();
  wennGespeichert(() => {
    if (offen === null) ziel?.replaceChildren();
  });
  document.querySelector<HTMLElement>(`.aufgabe-titel[data-aufgabe-link="${id}"]`)?.focus({ preventScroll: true });
}

/** Sichtbarkeit, aktive Zeile, Filter und Spalten nach dem Zustand richten – auch nach jedem Austausch in der Liste. */
export function seitenleisteAbgleichen() {
  const aussen = leiste();
  if (!aussen) return;
  aussen.hidden = offen === null;
  const huelle = raster();
  huelle?.classList.toggle("projekt-raster--offen", offen !== null);
  if (breite !== null) huelle?.style.setProperty("--seitenleiste-breite", `${breite}px`);
  document.querySelectorAll(".aufgabe-zeile--aktiv").forEach((zeile) => {
    zeile.classList.remove("aufgabe-zeile--aktiv");
    zeile.querySelector(".aufgabe-titel")?.removeAttribute("aria-current");
  });
  const zeile = offen ? document.getElementById(`aufgabe-${offen}`) : null;
  zeile?.classList.add("aufgabe-zeile--aktiv");
  zeile?.querySelector(".aufgabe-titel")?.setAttribute("aria-current", "true");
  const filter = document.getElementById("filter-aufgabe") as HTMLInputElement | null;
  if (filter) {
    filter.value = offen ?? "";
    filter.disabled = offen === null;
  }
  spaltenAnpassen();
}

function spaltenAnpassen() {
  const liste = document.getElementById("aufgaben-baum");
  const huelle = liste?.closest(".projekt-raster__liste");
  if (!liste || !huelle) return;
  const noetig = parseFloat(getComputedStyle(liste).getPropertyValue("--liste-min")) || 0;
  liste.classList.toggle("liste--kompakt", offen !== null && istBreit() && huelle.clientWidth < noetig);
}

/** Beim Laden und nach dem Wiederherstellen aus dem Verlauf: Zustand aus der Seite übernehmen. */
function ausSeiteLesen() {
  offen = document.getElementById("seitenleiste-inhalt")?.dataset.seitenleisteAufgabe ?? null;
  const huelle = document.querySelector(".projekt-raster__liste");
  beobachter?.disconnect();
  if (huelle) {
    beobachter = new ResizeObserver(spaltenAnpassen);
    beobachter.observe(huelle);
  }
  seitenleisteAbgleichen();
}

function ziehen(event: PointerEvent, griff: HTMLElement) {
  const aussen = leiste();
  const huelle = raster();
  if (!aussen || !huelle || event.pointerType !== "mouse" || event.button !== 0) return;
  event.preventDefault();
  const start = aussen.getBoundingClientRect().width;
  const x0 = event.clientX;
  griff.setPointerCapture(event.pointerId);
  huelle.classList.add("projekt-raster--zieht");
  const bewegen = (e: PointerEvent) => {
    breite = breiteBegrenzen(start + x0 - e.clientX, huelle.clientWidth);
    huelle.style.setProperty("--seitenleiste-breite", `${breite}px`);
  };
  const ende = () => {
    huelle.classList.remove("projekt-raster--zieht");
    griff.removeEventListener("pointermove", bewegen);
  };
  griff.addEventListener("pointermove", bewegen);
  griff.addEventListener("pointerup", ende, { once: true });
  griff.addEventListener("pointercancel", ende, { once: true });
}

export function initSeitenleiste() {
  // Schmales Fenster: ein Link mit ?aufgabe= führt wie jeder andere zur Detailseite
  const inhalt = document.getElementById("seitenleiste-inhalt");
  if (inhalt && !istBreit()) {
    location.replace(detailAdresse(inhalt.dataset.seitenleisteAufgabe!));
    return;
  }
  ausSeiteLesen();

  document.addEventListener("htmx:historyRestore", ausSeiteLesen);
  document.addEventListener("htmx:beforeRequest", (event) => {
    if ((event as CustomEvent).detail.requestConfig?.verb !== "get") laufend += 1;
  });
  document.addEventListener("htmx:afterRequest", (event) => {
    if ((event as CustomEvent).detail.requestConfig?.verb === "get") return;
    laufend = Math.max(0, laufend - 1);
    window.setTimeout(weiter); // die nächste Anfrage aus der Warteschlange startet erst nach diesem Ereignis
  });

  document.addEventListener("click", (event) => {
    const ziel = event.target as HTMLElement;
    if (ziel.closest("[data-seitenleiste-schliessen]")) {
      schliessen("neu");
      return;
    }
    const link = ziel.closest<HTMLAnchorElement>("a[data-aufgabe-link]");
    if (!link || !leiste() || !klickAbfangen(event, istBreit())) return;
    event.preventDefault();
    if (link.dataset.aufgabeLink !== offen) oeffnen(link.dataset.aufgabeLink!, true);
    platz()?.focus({ preventScroll: true });
  });

  document.addEventListener("pointerdown", (event) => {
    const griff = (event.target as HTMLElement).closest<HTMLElement>("[data-seitenleiste-griff]");
    if (griff) ziehen(event, griff);
  });

  // Erstes Esc verlässt ein Eingabefeld (und speichert es), das nächste schließt die Seitenleiste
  document.addEventListener("keydown", (event) => {
    if (event.key !== "Escape" || event.defaultPrevented || offen === null || !istBreit()) return;
    const feld = document.activeElement as HTMLElement | null;
    if (document.querySelector("dialog[open]") || feld?.closest(".kopf")) return;
    if (feld?.matches("input, textarea, select, [contenteditable]")) feld.blur();
    else schliessen("neu");
  });

  window.addEventListener("popstate", (event) => {
    if (event.state?.htmx || !leiste()) return;
    const id = aufgabeInAdresse(location.search);
    if (id === offen) return;
    if (id) oeffnen(id, false);
    else schliessen("keine");
  });

  // Ereignisse vom Server (HX-Trigger-After-Settle) und vom Ziehen in der Liste
  document.addEventListener("aufgabe-geaendert", (event) => {
    const ids = (event as CustomEvent).detail.ids as number[];
    if (offen && ids.map(String).includes(offen)) laden(offen, false);
  });
  document.addEventListener("seitenleiste-schliessen", () => schliessen("ersetzen"));
}
