/**
 * Seitennavigation am Desktop: steht still, nur die Projektliste scrollt (Stile in app.css).
 * Hier: Höhe der Kopfzeile als CSS-Variable nachführen, Schatten an den Rändern der Projektliste,
 * hinter denen noch Einträge liegen, Scrollposition der Liste beim Seitenwechsel behalten und das
 * aktive Projekt in den sichtbaren Bereich holen.
 */
const SPEICHER = "seitennav-projekte";
/** Abstand zum Rand beim Hereinholen des aktiven Projekts, damit der Schatten es nicht verdeckt */
const PUFFER = 12;

export type Raender = { ueberlauf: boolean; mehrOben: boolean; mehrUnten: boolean };

/** Ob die Liste überläuft und ob über bzw. unter dem sichtbaren Teil noch Einträge liegen. */
export function raender(scrollTop: number, scrollHeight: number, clientHeight: number): Raender {
  // 1 px Toleranz: Chromium rundet scrollTop bei Zoom auf Bruchteile
  const ueberlauf = scrollHeight - clientHeight > 1;
  return {
    ueberlauf,
    mehrOben: ueberlauf && scrollTop > 1,
    mehrUnten: ueberlauf && scrollTop + clientHeight < scrollHeight - 1,
  };
}

/**
 * Neue Scrollposition, damit ein Eintrag ganz sichtbar ist (wie scrollIntoView mit
 * block: "nearest", aber nur für die Liste, nie für die Seite). Koordinaten relativ zum Fenster.
 */
export function sichtbarePosition(
  scrollTop: number, liste: { top: number; bottom: number }, eintrag: { top: number; bottom: number },
  puffer = PUFFER,
): number {
  const hoehe = liste.bottom - liste.top;
  if (eintrag.bottom - eintrag.top + 2 * puffer > hoehe) return scrollTop + eintrag.top - liste.top - puffer;
  if (eintrag.top < liste.top + puffer) return scrollTop - (liste.top + puffer - eintrag.top);
  if (eintrag.bottom > liste.bottom - puffer) return scrollTop + (eintrag.bottom - (liste.bottom - puffer));
  return scrollTop;
}

function lesen(): number | null {
  try {
    const wert = Number(sessionStorage.getItem(SPEICHER));
    return Number.isFinite(wert) && wert > 0 ? wert : null;
  } catch {
    return null;
  }
}

function schreiben(wert: number): void {
  try {
    sessionStorage.setItem(SPEICHER, String(Math.round(wert)));
  } catch {
    // ohne Speicher beginnt die Liste nach dem Seitenwechsel oben
  }
}

function kopfhoeheNachfuehren(): void {
  const kopf = document.querySelector<HTMLElement>(".kopf");
  if (!kopf || typeof ResizeObserver === "undefined") return;
  const setzen = () => document.documentElement.style.setProperty("--kopf-hoehe", `${kopf.offsetHeight}px`);
  new ResizeObserver(setzen).observe(kopf);
  setzen();
}

export function initSeitennav(): void {
  kopfhoeheNachfuehren();
  const liste = document.querySelector<HTMLElement>("[data-projektliste]");
  if (!liste) return;

  // Zustand an der Liste (Tests, Verhalten) und am Rahmen darum (Fläche, Linien, Schatten)
  const ziele = [liste, liste.closest<HTMLElement>("[data-projektrahmen]")].filter((e): e is HTMLElement => e !== null);
  const anzeigen = () => {
    const r = raender(liste.scrollTop, liste.scrollHeight, liste.clientHeight);
    for (const ziel of ziele) {
      ziel.toggleAttribute("data-ueberlauf", r.ueberlauf);
      ziel.toggleAttribute("data-mehr-oben", r.mehrOben);
      ziel.toggleAttribute("data-mehr-unten", r.mehrUnten);
    }
  };

  const vorher = lesen();
  if (vorher !== null) liste.scrollTop = vorher;
  const aktiv = liste.querySelector<HTMLElement>("[aria-current='page']");
  // Am Handy (Menü zugeklappt) hat die Liste keine Höhe, dort nichts verschieben
  if (aktiv && liste.clientHeight > 0) {
    liste.scrollTop = sichtbarePosition(liste.scrollTop, liste.getBoundingClientRect(), aktiv.getBoundingClientRect());
  }
  anzeigen();

  let geplant = false;
  liste.addEventListener("scroll", () => {
    if (geplant) return;
    geplant = true;
    requestAnimationFrame(() => {
      geplant = false;
      anzeigen();
      schreiben(liste.scrollTop);
    });
  }, { passive: true });
  if (typeof ResizeObserver !== "undefined") new ResizeObserver(anzeigen).observe(liste);
}
