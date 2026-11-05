import Sortable from "sortablejs";
import { csrfToken } from "./csrf";

/**
 * Listen mit data-sortierbar="<url>" lassen sich per Drag-and-drop umsortieren
 * (Abschnitte; Aufgaben siehe aufgabenbaum.ts). Die neue Reihenfolge wird als
 * {"ids": [...], "gruppe": "..."} an die URL geschickt.
 */
export function initSortierbar(wurzel: ParentNode) {
  wurzel.querySelectorAll<HTMLElement>("[data-sortierbar]").forEach((liste) => {
    if ((liste as HTMLElement & { _sortable?: Sortable })._sortable) return;
    const instanz = Sortable.create(liste, {
      handle: liste.dataset.griff || ".ziehgriff",
      draggable: liste.dataset.element || "[data-id]",
      group: liste.dataset.gruppe ? { name: liste.dataset.gruppe } : undefined,
      animation: 120,
      onEnd: (event) => {
        const ziele = new Set([event.from, event.to]);
        ziele.forEach((ziel) => {
          const url = (ziel as HTMLElement).dataset.sortierbar;
          if (!url) return;
          const ids = Array.from(ziel.querySelectorAll<HTMLElement>(":scope > [data-id]")).map((el) => el.dataset.id);
          fetch(url, {
            method: "POST",
            headers: { "Content-Type": "application/json", "X-CSRFToken": csrfToken() },
            body: JSON.stringify({ ids, ziel: (ziel as HTMLElement).dataset.zielId ?? null }),
          }).then((antwort) => {
            // Fehler oder abgelaufene Sitzung (Weiterleitung zur Anmeldung): Seite neu laden
            if (!antwort.ok || antwort.redirected) window.location.reload();
          });
        });
      },
    });
    (liste as HTMLElement & { _sortable?: Sortable })._sortable = instanz;
  });
}
