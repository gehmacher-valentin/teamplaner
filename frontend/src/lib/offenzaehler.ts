// Zähler offener Zeilen nach dem Abhaken (lib/abhaken.ts), ohne HTMX – damit auch im Test nutzbar.

/** Offene Zeilen einer Karte zählen ([data-zaehlen]): Zähler im Kopf, je Gruppe, Leer-Meldung. */
export function zaehlerAktualisieren(karte: Element | null) {
  if (!karte?.hasAttribute("data-zaehlen")) return;
  karte.querySelectorAll<HTMLElement>("[data-gruppe]").forEach((gruppe) => {
    const zeilen = gruppe.querySelectorAll("[data-zeile]");
    if (!zeilen.length) {
      gruppe.remove();
      return;
    }
    const zahl = gruppe.querySelector("[data-gruppe-zahl]");
    if (zahl) zahl.textContent = String(gruppe.querySelectorAll("[data-zeile]:not([data-erledigt])").length);
  });
  const offen = karte.querySelectorAll("[data-zeile]:not([data-erledigt])").length;
  const zaehler = karte.querySelector("[data-zaehler]");
  if (zaehler) zaehler.textContent = String(offen);
  const leer = karte.querySelector<HTMLElement>("[data-leer]");
  if (leer) leer.hidden = karte.querySelectorAll("[data-zeile]").length > 0;
}
