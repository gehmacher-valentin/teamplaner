/**
 * Sofort speichernde Bedienelemente: Schalter, Auswahlen, Umschalter und Textfelder, die per HTMX ohne
 * Austausch speichern (hx-swap="none"). Klappt das Speichern nicht, springen sie auf den zuletzt
 * gespeicherten Wert zurück; ein Bereich mit data-sofort-bereich wird dabei als Ganzes zurückgesetzt
 * (z. B. der Kategorie-Schalter samt seinen Ereignissen).
 *
 * Nach dem Neuladen (z. B. HX-Refresh nach Sprache oder Farbschema) stellt Firefox die zuletzt gewählten
 * Werte von Formularfeldern wieder her und überschreibt damit den Stand vom Server. Dagegen helfen
 * autocomplete="off" in den Vorlagen und hier das Zurücksetzen auf die vom Server gelieferten Werte.
 */
type Feld = HTMLInputElement | HTMLSelectElement;

function felder(el: HTMLElement): Feld[] {
  const bereich = el.closest<HTMLElement>("[data-sofort-bereich]") ?? el;
  const liste = Array.from(bereich.querySelectorAll<Feld>("input, select"));
  if (el.matches("input, select")) liste.push(el as Feld);
  return liste;
}

function merken(el: HTMLElement) {
  for (const f of felder(el)) {
    if (f instanceof HTMLSelectElement) Array.from(f.options).forEach((o) => (o.defaultSelected = o.selected));
    else if (f.type === "checkbox" || f.type === "radio") f.defaultChecked = f.checked;
    else if (f.type === "text") f.defaultValue = f.value;
  }
}

function zuruecksetzen(el: HTMLElement) {
  for (const f of felder(el)) {
    if (f instanceof HTMLSelectElement) Array.from(f.options).forEach((o) => (o.selected = o.defaultSelected));
    else if (f.type === "checkbox" || f.type === "radio") f.checked = f.defaultChecked;
    else if (f.type === "text") f.value = f.defaultValue;
  }
}

function sofort(el: EventTarget | null): el is HTMLElement {
  return el instanceof HTMLElement && el.getAttribute("hx-swap") === "none" && !el.closest("[data-listen-bearbeiten]");
}

/** Alle sofort speichernden Felder auf den Stand vom Server (nicht aus dem Zurück-Cache: der ist aktuell). */
export function serverstandHerstellen(wurzel: ParentNode = document) {
  wurzel.querySelectorAll<HTMLElement>('[hx-swap="none"]').forEach((el) => {
    if (el.matches("input, select") && sofort(el)) zuruecksetzen(el);
  });
}

export function initSofort() {
  serverstandHerstellen();
  window.addEventListener("pageshow", (event) => {
    if (!event.persisted) serverstandHerstellen();
  });
  document.addEventListener("htmx:afterRequest", (event) => {
    const el = event.target;
    if (!sofort(el)) return;
    if ((event as CustomEvent).detail.successful) merken(el);
    else zuruecksetzen(el);
  });
  document.addEventListener("htmx:sendError", (event) => {
    if (sofort(event.target)) zuruecksetzen(event.target);
  });
}
