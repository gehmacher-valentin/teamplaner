/**
 * Freitext mit Vorschlägen beim Tippen („Lieferant“ in den Bestellungen): Ein Feld mit
 * data-vorschlaege="<id>" holt seine Vorschläge aus den <option>-Elementen des Elements mit dieser id
 * (ein <datalist>, das der Server mitliefert und bei jeder HTMX-Aktualisierung neu schickt). Das native
 * Datalist-Popup wird nicht benutzt, weil Browser unterschiedlich filtern und es sich nicht gestalten lässt.
 * Freier Text bleibt möglich; gespeichert wird wie bei jedem Inline-Feld über das change-Ereignis.
 */
import { passt } from "./personenwahl";

let zaehler = 0;

/** Vorschläge, die zur Eingabe passen (Groß-/Kleinschreibung und Akzente egal, Treffer irgendwo im Namen). */
export function vorschlaegeFiltern(alle: string[], suche: string): string[] {
  const s = suche.trim();
  return s ? alle.filter((v) => passt(v, s)) : alle.slice();
}

export function initVorschlaege(wurzel: ParentNode) {
  wurzel
    .querySelectorAll<HTMLInputElement | HTMLTextAreaElement>("input[data-vorschlaege], textarea[data-vorschlaege]")
    .forEach((feld) => vorschlaegeEinrichten(feld));
}

export function vorschlaegeEinrichten(feld: HTMLInputElement | HTMLTextAreaElement) {
  if (feld.dataset.vorschlaegeFertig) return;
  feld.dataset.vorschlaegeFertig = "1";
  const id = `vorschlaege-${++zaehler}`;
  const liste = document.createElement("ul");
  liste.className = "personenwahl__liste vorschlaege__liste";
  liste.id = `${id}-liste`;
  liste.setAttribute("role", "listbox");
  const name = feld.getAttribute("aria-label");
  if (name) liste.setAttribute("aria-label", name);
  liste.hidden = true;
  feld.after(liste);
  feld.setAttribute("role", "combobox");
  feld.setAttribute("aria-autocomplete", "list");
  feld.setAttribute("aria-expanded", "false");
  feld.setAttribute("aria-controls", liste.id);
  feld.autocomplete = "off";

  let treffer: string[] = [];
  let aktiv = -1; // nichts vorausgewählt: Enter speichert den getippten Text
  let getippt = false;

  const alle = () => {
    const quelle = document.getElementById(feld.dataset.vorschlaege ?? "");
    return quelle ? Array.from(quelle.querySelectorAll("option"), (o) => o.value).filter(Boolean) : [];
  };
  const zeichnen = () => {
    treffer = vorschlaegeFiltern(alle(), getippt ? feld.value : "");
    if (aktiv >= treffer.length) aktiv = treffer.length - 1;
    liste.replaceChildren(...treffer.map((text, i) => {
      const li = document.createElement("li");
      li.id = `${id}-${i}`;
      li.setAttribute("role", "option");
      li.setAttribute("aria-selected", String(i === aktiv));
      li.dataset.index = String(i);
      li.textContent = text;
      li.className = `personenwahl__option${i === aktiv ? " personenwahl__option--aktiv" : ""}`;
      return li;
    }));
    // Ohne Treffer keine leere Liste zeigen – freier Text ist ja erlaubt
    liste.hidden = treffer.length === 0;
    feld.setAttribute("aria-expanded", String(!liste.hidden));
    if (aktiv >= 0 && !liste.hidden) {
      feld.setAttribute("aria-activedescendant", `${id}-${aktiv}`);
      const li = liste.children[aktiv] as HTMLElement;
      if (li.offsetTop < liste.scrollTop) liste.scrollTop = li.offsetTop;
      else if (li.offsetTop + li.offsetHeight > liste.scrollTop + liste.clientHeight) {
        liste.scrollTop = li.offsetTop + li.offsetHeight - liste.clientHeight;
      }
    } else {
      feld.removeAttribute("aria-activedescendant");
    }
  };
  // Fest positioniert: die Bestellliste scrollt waagrecht und darf die Liste nicht abschneiden
  const position = () => {
    const r = feld.getBoundingClientRect();
    liste.style.left = `${r.left}px`;
    liste.style.minWidth = `${r.width}px`;
    const unten = window.innerHeight - r.bottom;
    if (unten < 220 && r.top > unten) {
      liste.style.top = "";
      liste.style.bottom = `${window.innerHeight - r.top + 2}px`;
    } else {
      liste.style.bottom = "";
      liste.style.top = `${r.bottom + 2}px`;
    }
  };
  let offen = false;
  const oeffnen = () => {
    if (feld.disabled || feld.readOnly || offen) return;
    offen = true;
    position();
    zeichnen();
    window.addEventListener("scroll", position, true);
    window.addEventListener("resize", position);
  };
  const schliessen = () => {
    offen = false;
    getippt = false;
    aktiv = -1;
    liste.hidden = true;
    feld.setAttribute("aria-expanded", "false");
    feld.removeAttribute("aria-activedescendant");
    window.removeEventListener("scroll", position, true);
    window.removeEventListener("resize", position);
  };
  let intern = false;
  const waehlen = (text: string) => {
    schliessen();
    if (feld.value === text) return;
    feld.value = text;
    intern = true;
    feld.dispatchEvent(new Event("input", { bubbles: true })); // mitwachsende Textfelder anpassen
    intern = false;
    feld.dispatchEvent(new Event("change", { bubbles: true })); // speichern wie beim Verlassen
  };

  feld.addEventListener("focus", oeffnen);
  feld.addEventListener("click", oeffnen);
  feld.addEventListener("input", () => {
    if (intern) return; // eigenes input-Ereignis aus waehlen()
    getippt = true;
    aktiv = -1;
    if (!offen) oeffnen();
    else zeichnen();
  });
  // Läuft vor lib/inline.ts (das am document lauscht): Enter/Esc gehören hier der offenen Liste
  const tasten = (ev: KeyboardEvent) => {
    if (ev.key === "ArrowDown" || ev.key === "ArrowUp") {
      ev.preventDefault();
      if (!offen) oeffnen();
      if (!treffer.length) return;
      aktiv = ev.key === "ArrowDown" ? Math.min(aktiv + 1, treffer.length - 1) : Math.max(aktiv - 1, 0);
      zeichnen();
    } else if (ev.key === "Enter" && !liste.hidden && treffer[aktiv] !== undefined) {
      ev.preventDefault();
      ev.stopPropagation();
      waehlen(treffer[aktiv]);
    } else if (ev.key === "Escape" && !liste.hidden) {
      ev.preventDefault();
      ev.stopPropagation(); // erst die Liste schließen, ein zweites Esc stellt den Wert zurück
      schliessen();
    } else if (ev.key === "Tab") {
      schliessen();
    }
  };
  feld.addEventListener("keydown", tasten as EventListener);
  feld.addEventListener("blur", schliessen);
  liste.addEventListener("mousedown", (ev) => ev.preventDefault()); // Fokus im Feld lassen
  liste.addEventListener("click", (ev) => {
    const li = (ev.target as HTMLElement).closest<HTMLElement>("[data-index]");
    if (li) waehlen(treffer[Number(li.dataset.index)]);
  });
}
