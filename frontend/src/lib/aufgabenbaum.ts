import htmx from "htmx.org";
import Sortable from "sortablejs";
import { csrfToken } from "./csrf";

type MitSortable = HTMLElement & { _sortable?: Sortable };

/**
 * Projektliste als Baum: Aufgaben am Griff ziehen – innerhalb eines Abschnitts, in einen
 * anderen Abschnitt, in eine andere Aufgabe hinein (wird ihre Unteraufgabe) oder aus ihr heraus
 * (eine Ebene höher). Jede Liste [data-aufgaben-liste] ist ein Sortable derselben Gruppe; tiefer als
 * data-max-ebenen lässt sich nichts ablegen. Gespeichert wird als {id, eltern, abschnitt, vor}; danach
 * lädt die Liste neu, damit Zähler und Einrückung stimmen.
 */
export function initAufgabenBaum(wurzel: ParentNode) {
  const listen = Array.from(wurzel.querySelectorAll<MitSortable>("[data-aufgaben-liste]"));
  if (wurzel instanceof HTMLElement && wurzel.matches("[data-aufgaben-liste]")) listen.unshift(wurzel);
  for (const liste of listen) {
    const baum = liste.closest<HTMLElement>("[data-aufgaben-baum]");
    if (!baum || liste._sortable) continue;
    const url = baum.dataset.aufgabenBaum!;
    const maxEbenen = Number(baum.dataset.maxEbenen ?? 0);
    liste._sortable = Sortable.create(liste, {
      group: { name: url },
      handle: ".aufgabe-griff",
      draggable: ".aufgabe-block",
      filter: ".aufgabe-block--waise",
      preventOnFilter: false,
      fallbackOnBody: true,
      swapThreshold: 0.65,
      emptyInsertThreshold: 6,
      animation: 120,
      onStart: () => baum.classList.add("aufgaben-baum--zieht"),
      // Ablegen nur, wo die gezogene Aufgabe samt ihren Unteraufgaben noch in die erlaubte Tiefe passt
      onMove: (ev) => {
        const tiefe = Number((ev.to as HTMLElement).dataset.tiefe ?? 0);
        const hoehe = Number((ev.dragged as HTMLElement).dataset.hoehe ?? 0);
        return tiefe + hoehe <= maxEbenen;
      },
      onEnd: (ev) => {
        baum.classList.remove("aufgaben-baum--zieht");
        if (ev.from === ev.to && ev.oldIndex === ev.newIndex) return;
        const block = ev.item as HTMLElement;
        const ziel = ev.to as HTMLElement;
        let vor = block.nextElementSibling as HTMLElement | null;
        while (vor && (!vor.matches(".aufgabe-block") || vor.matches(".aufgabe-block--waise"))) {
          vor = vor.nextElementSibling as HTMLElement | null;
        }
        fetch(url, {
          method: "POST",
          headers: { "Content-Type": "application/json", "X-CSRFToken": csrfToken() },
          body: JSON.stringify({
            id: block.dataset.id,
            eltern: ziel.dataset.eltern || null,
            abschnitt: ziel.dataset.abschnitt || null,
            vor: vor?.dataset.id ?? null,
          }),
        }).then((antwort) => {
          // Fehler oder abgelaufene Sitzung (Weiterleitung zur Anmeldung): Seite neu laden
          if (!antwort.ok || antwort.redirected) window.location.reload();
          else if (ev.from !== ev.to) neuLaden(baum);
          // Verschieben erhöht die Version: eine offene Seitenleiste zieht nach
          document.dispatchEvent(new CustomEvent("aufgabe-geaendert", { detail: { ids: [Number(block.dataset.id)] } }));
        }, () => window.location.reload());
      },
    });
  }
}

function neuLaden(baum: HTMLElement) {
  const ziel = `#${baum.id}`;
  htmx.ajax("get", window.location.href, { target: ziel, select: ziel, swap: "outerHTML" });
}
