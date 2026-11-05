/**
 * Spaltenbreiten aller Listen verstellen: an der Grenze zweier Spalten in der Kopfzeile
 * (.liste__kopf) ziehen, Doppelklick setzt die Spalte auf ihre Standardbreite zurück. Nur mit der
 * Maus; nichts wird gespeichert – nach dem Neuladen gilt wieder die Standardbreite.
 *
 * Die Breiten stehen als feste px in --spalten am <section class="liste">, --liste-min wächst mit.
 * HTMX tauscht meist nur den Inhalt darin aus; wird die ganze Liste ersetzt (Filter der
 * Projektliste), stellt das Modul die Breiten anhand der ID der Liste wieder her.
 */

export const MINDESTBREITE = 48;

/** Breite der Spalte ``index`` um ``delta`` px ändern, nie schmäler als die Mindestbreite. */
export function breiteAendern(breiten: number[], index: number, delta: number, min = MINDESTBREITE): number[] {
  return breiten.map((b, i) => (i === index ? Math.max(min, Math.round(b + delta)) : b));
}

/** Eine Spalte auf ihre Standardbreite zurücksetzen, die anderen bleiben. */
export function zuruecksetzen(breiten: number[], standard: number[], index: number): number[] {
  return breiten.map((b, i) => (i === index ? standard[i] ?? b : b));
}

/** „120px 64.5px 200px“ (getComputedStyle) → [120, 64.5, 200] */
export function pxListe(text: string): number[] {
  return text.trim().split(/\s+/).map((teil) => parseFloat(teil)).filter((n) => Number.isFinite(n));
}

/** Mindestbreite der ganzen Liste: Spalten, Abstände dazwischen und Innenabstand der Zeile. */
export function listenbreite(breiten: number[], abstand: number, polster: number): number {
  return Math.ceil(breiten.reduce((s, b) => s + b, 0) + abstand * Math.max(0, breiten.length - 1) + polster);
}

interface Zustand {
  standard: number[];
  breiten: number[];
}

// Bis zum Neuladen: eingestellte Breiten je Liste (ID), damit sie ein HTMX-Austausch überlebt
const merker = new Map<string, Zustand>();

function anwenden(liste: HTMLElement, kopf: HTMLElement, zustand: Zustand) {
  const stil = getComputedStyle(kopf);
  const abstand = parseFloat(stil.columnGap) || 0;
  const polster = (parseFloat(stil.paddingLeft) || 0) + (parseFloat(stil.paddingRight) || 0);
  liste.style.setProperty("--spalten", zustand.breiten.map((b) => `${b}px`).join(" "));
  liste.style.setProperty("--liste-min", `${listenbreite(zustand.breiten, abstand, polster)}px`);
  if (liste.id) merker.set(liste.id, zustand);
}

function einrichten(kopf: HTMLElement) {
  const liste = kopf.closest<HTMLElement>(".liste");
  if (!liste || kopf.dataset.spaltenVerstellbar || liste.hasAttribute("data-spalten-fest")) return;
  kopf.dataset.spaltenVerstellbar = "1";
  const zellen = Array.from(kopf.children) as HTMLElement[];
  let zustand: Zustand | null = liste.id ? merker.get(liste.id) ?? null : null;
  if (zustand) anwenden(liste, kopf, zustand);

  const aktuell = (): Zustand => {
    if (!zustand) {
      const breiten = pxListe(getComputedStyle(kopf).gridTemplateColumns);
      zustand = { standard: breiten, breiten };
    }
    return zustand;
  };

  zellen.slice(0, -1).forEach((zelle, index) => {
    const griff = document.createElement("span");
    griff.className = "spaltengriff";
    griff.setAttribute("aria-hidden", "true");
    zelle.append(griff);
    griff.addEventListener("pointerdown", (event) => {
      if (event.pointerType !== "mouse" || event.button !== 0) return;
      event.preventDefault();
      const start = aktuell();
      const x0 = event.clientX;
      griff.setPointerCapture(event.pointerId);
      liste.classList.add("liste--verstellt");
      const bewegen = (e: PointerEvent) => {
        zustand = { standard: start.standard, breiten: breiteAendern(start.breiten, index, e.clientX - x0) };
        anwenden(liste, kopf, zustand);
      };
      const ende = () => {
        liste.classList.remove("liste--verstellt");
        griff.removeEventListener("pointermove", bewegen);
      };
      griff.addEventListener("pointermove", bewegen);
      griff.addEventListener("pointerup", ende, { once: true });
      griff.addEventListener("pointercancel", ende, { once: true });
    });
    griff.addEventListener("dblclick", (event) => {
      event.preventDefault();
      const z = aktuell();
      zustand = { standard: z.standard, breiten: zuruecksetzen(z.breiten, z.standard, index) };
      anwenden(liste, kopf, zustand);
    });
  });
}

export function initSpaltenbreiten(wurzel: ParentNode) {
  wurzel.querySelectorAll<HTMLElement>(".liste .liste__kopf").forEach(einrichten);
  if (wurzel instanceof HTMLElement && wurzel.matches(".liste__kopf")) einrichten(wurzel);
}
