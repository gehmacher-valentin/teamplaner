/**
 * Listen-Editor: Eine Zeile im Bearbeiten-Modus speichert jede Änderung sofort (hx-trigger="change").
 * Enter, Esc, ✓ oder das Verlassen der Zeile beenden das Bearbeiten – erst nachdem gespeichert ist; bei
 * einem Fehler (Antwort mit X-Fehler) bleibt die Zeile offen und zeigt ihn am Feld.
 */
import htmx from "htmx.org";

const laeuft = new WeakMap<HTMLElement, number>();
const fertigGewuenscht = new WeakSet<HTMLElement>();

function zeileVon(el: EventTarget | null) {
  return el instanceof HTMLElement ? el.closest<HTMLElement>("[data-listen-bearbeiten]") : null;
}

function fertig(zeile: HTMLElement) {
  if (!zeile.isConnected) return;
  if (laeuft.get(zeile)) {
    fertigGewuenscht.add(zeile);
    return;
  }
  htmx.ajax("get", zeile.dataset.listenBearbeiten!, { target: zeile, swap: "outerHTML" });
}

export function initListeneditor() {
  document.addEventListener("htmx:beforeRequest", (event) => {
    const zeile = zeileVon(event.target);
    if (zeile && (event as CustomEvent).detail.requestConfig?.verb === "post") laeuft.set(zeile, (laeuft.get(zeile) ?? 0) + 1);
  });
  document.addEventListener("htmx:afterRequest", (event) => {
    const zeile = zeileVon(event.target);
    if (!zeile || (event as CustomEvent).detail.requestConfig?.verb !== "post") return;
    laeuft.set(zeile, Math.max(0, (laeuft.get(zeile) ?? 1) - 1));
    const xhr = (event as CustomEvent).detail.xhr as XMLHttpRequest | undefined;
    if (xhr?.getResponseHeader("X-Fehler")) fertigGewuenscht.delete(zeile);
    else if (!laeuft.get(zeile) && fertigGewuenscht.has(zeile)) {
      fertigGewuenscht.delete(zeile);
      fertig(zeile);
    }
  });
  // Fokus verlässt die Zeile (Enter und Esc in data-inline-Feldern verlassen das Feld ebenfalls)
  document.addEventListener("focusout", (event) => {
    const zeile = zeileVon(event.target);
    if (zeile && !zeile.contains(event.relatedTarget as Node | null)) window.setTimeout(() => fertig(zeile));
  });
  document.addEventListener("click", (event) => {
    const knopf = (event.target as HTMLElement).closest("[data-listen-fertig]");
    const zeile = zeileVon(knopf);
    if (zeile) fertig(zeile);
  });
  // Vorschau des Status-Badges: Name und Farbe
  document.addEventListener("input", (event) => {
    const feld = event.target;
    const zeile = zeileVon(feld);
    const vorschau = zeile?.querySelector<HTMLElement>("[data-vorschau]");
    if (!vorschau || !(feld instanceof HTMLInputElement)) return;
    if (feld.type === "text") vorschau.textContent = feld.value;
    if (feld.type === "radio" && feld.checked) vorschau.className = `badge st-${feld.value} einst-zeile__vorschau`;
  });
}
