/**
 * Reihenfolge per Ziehen am Griff oder mit den Pfeiltasten:
 * Container mit data-reihenfolge="<URL>", Zeilen mit data-id, Griff [data-reihenfolge-griff].
 * Gespeichert wird als {"ids": [...]}; die Rückmeldung kommt als Toast.
 */
import Sortable from "sortablejs";
import { csrfToken, zurAnmeldung } from "./csrf";
import { t } from "./texte";
import { toast } from "./toast";

type MitSortable = HTMLElement & { _sortable?: Sortable };

function zeilen(liste: HTMLElement) {
  return Array.from(liste.children).filter((el): el is HTMLElement => el instanceof HTMLElement && !!el.dataset.id);
}

async function speichern(liste: HTMLElement) {
  try {
    const antwort = await fetch(liste.dataset.reihenfolge!, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-CSRFToken": csrfToken(), "HX-Request": "true" },
      credentials: "same-origin",
      body: JSON.stringify({ ids: zeilen(liste).map((z) => Number(z.dataset.id)) }),
    });
    if (antwort.redirected) return zurAnmeldung();
    if (!antwort.ok) throw new Error(String(antwort.status));
    toast(t("gespeichert"));
  } catch {
    toast(t("speichern_fehlgeschlagen"), { art: "fehler" });
  }
}

export function initReihenfolge(wurzel: ParentNode) {
  const listen = Array.from(wurzel.querySelectorAll<MitSortable>("[data-reihenfolge]"));
  if (wurzel instanceof HTMLElement && wurzel.matches("[data-reihenfolge]")) listen.unshift(wurzel as MitSortable);
  for (const liste of listen) {
    if (liste._sortable) continue;
    liste._sortable = Sortable.create(liste, {
      handle: "[data-reihenfolge-griff]",
      draggable: "[data-id]",
      animation: 120,
      onEnd: (ev) => {
        if (ev.oldIndex !== ev.newIndex) speichern(liste);
      },
    });
  }
}

// Mit der Tastatur: Pfeil hoch/runter auf dem Griff verschiebt die Zeile um eine Stelle
document.addEventListener("keydown", (event) => {
  const griff = (event.target as HTMLElement).closest?.<HTMLElement>("[data-reihenfolge-griff]");
  if (!griff || (event.key !== "ArrowUp" && event.key !== "ArrowDown")) return;
  const zeile = griff.closest<HTMLElement>("[data-id]");
  const liste = zeile?.parentElement;
  if (!zeile || !liste?.dataset.reihenfolge) return;
  event.preventDefault();
  const nachbar = event.key === "ArrowUp" ? zeile.previousElementSibling : zeile.nextElementSibling;
  if (!(nachbar instanceof HTMLElement) || !nachbar.dataset.id) return;
  if (event.key === "ArrowUp") nachbar.before(zeile);
  else nachbar.after(zeile);
  griff.focus();
  speichern(liste);
});
