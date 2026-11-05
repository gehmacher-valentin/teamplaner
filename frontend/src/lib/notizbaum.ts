/**
 * Ordnerspalte der Notizen als Baum. Der Pfeil klappt einen Ordner auf und zu, der Name führt
 * zur Ordnerübersicht. Aufgeklappte Ordner bleiben offen, solange der Browser-Tab offen ist
 * (sessionStorage); am Handy ist nur der Ordner der aktuellen Seite offen (vom Server gesetzt).
 */
const SPEICHER = "notizbaum-offen";

function lesen(): Set<string> {
  try {
    const roh: unknown = JSON.parse(sessionStorage.getItem(SPEICHER) ?? "[]");
    return new Set(Array.isArray(roh) ? roh.map(String) : []);
  } catch {
    return new Set();
  }
}

function schreiben(offen: Set<string>): void {
  try {
    sessionStorage.setItem(SPEICHER, JSON.stringify([...offen]));
  } catch {
    // ohne Speicher bleibt nur der aktuelle Ordner offen
  }
}

export function initNotizbaum(): void {
  const spalte = document.querySelector<HTMLElement>("[data-notizbaum]");
  if (!spalte) return;
  const merken = !window.matchMedia("(max-width: 760px)").matches;
  const offen = merken ? lesen() : new Set<string>();
  for (const knopf of spalte.querySelectorAll<HTMLButtonElement>("[data-ordner-schalter]")) {
    const ordner = knopf.dataset.ordnerSchalter ?? "";
    if (knopf.getAttribute("aria-expanded") === "true") offen.add(ordner);
    else if (offen.has(ordner)) knopf.setAttribute("aria-expanded", "true");
  }
  if (merken) schreiben(offen);

  spalte.addEventListener("click", (e) => {
    const ziel = e.target as Element;
    const knopf = ziel.closest<HTMLButtonElement>("[data-ordner-schalter]");
    const link = ziel.closest<HTMLElement>("[data-ordner-link]");
    if (!knopf && !link) return;
    const ordner = (knopf ? knopf.dataset.ordnerSchalter : link?.dataset.ordnerLink) ?? "";
    const auf = knopf ? knopf.getAttribute("aria-expanded") !== "true" : true;
    knopf?.setAttribute("aria-expanded", String(auf));
    if (!merken) return;
    const gemerkt = lesen();
    if (auf) gemerkt.add(ordner);
    else gemerkt.delete(ordner);
    schreiben(gemerkt);
  });
}
