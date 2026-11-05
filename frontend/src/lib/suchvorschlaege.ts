/**
 * Vorschläge beim Tippen in der Suche der Kopfzeile: HTMX holt nach kurzer Pause die besten
 * Treffer (projekte.views.suche_vorschlaege) in die Liste unter dem Feld. Hier nur Anzeigen/Schließen und die
 * Tastatur: Pfeile wählen einen Treffer, Enter öffnet ihn (ohne Auswahl die volle Suchseite), Escape schließt.
 */

/** Nächster Index beim Blättern mit den Pfeiltasten; -1 = nichts gewählt (zurück im Eingabefeld). */
export function naechsterIndex(aktiv: number, anzahl: number, richtung: 1 | -1): number {
  if (anzahl === 0) return -1;
  if (richtung === 1) return Math.min(aktiv + 1, anzahl - 1);
  return aktiv <= 0 ? -1 : aktiv - 1;
}

export function initSuchvorschlaege() {
  const feld = document.querySelector<HTMLInputElement>("input[data-suchvorschlaege]");
  const liste = document.getElementById("suchvorschlaege");
  const formular = feld?.form;
  if (!feld || !liste || !formular) return;

  let aktiv = -1;
  const optionen = () => Array.from(liste.querySelectorAll<HTMLAnchorElement>(".suchvorschlag"));

  const markieren = (index: number) => {
    aktiv = index;
    optionen().forEach((o, i) => {
      o.classList.toggle("suchvorschlag--aktiv", i === aktiv);
      o.setAttribute("aria-selected", String(i === aktiv));
    });
    const gewaehlt = optionen()[aktiv];
    if (gewaehlt) {
      feld.setAttribute("aria-activedescendant", gewaehlt.id);
      gewaehlt.scrollIntoView({ block: "nearest" });
    } else {
      feld.removeAttribute("aria-activedescendant");
    }
  };
  const oeffnen = () => {
    if (!liste.childElementCount) return;
    liste.hidden = false;
    feld.setAttribute("aria-expanded", "true");
  };
  const schliessen = () => {
    liste.hidden = true;
    feld.setAttribute("aria-expanded", "false");
    markieren(-1);
  };

  // Neue Treffer eingetroffen: Kennungen für aria-activedescendant vergeben, zeigen solange das Feld Fokus hat
  document.addEventListener("htmx:afterSwap", (event) => {
    if ((event as CustomEvent).detail.target !== liste) return;
    optionen().forEach((o, i) => { o.id = `suchvorschlag-${i}`; });
    aktiv = -1;
    feld.removeAttribute("aria-activedescendant");
    if (liste.childElementCount && document.activeElement === feld) oeffnen();
    else schliessen();
  });

  feld.addEventListener("focus", () => {
    if (feld.value.trim()) oeffnen();
  });
  feld.addEventListener("input", () => {
    if (!feld.value.trim()) schliessen();
  });
  feld.addEventListener("keydown", (event) => {
    const anzahl = optionen().length;
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      if (!anzahl) return;
      event.preventDefault();
      if (liste.hidden) oeffnen();
      markieren(naechsterIndex(aktiv, anzahl, event.key === "ArrowDown" ? 1 : -1));
    } else if (event.key === "Enter" && !liste.hidden && aktiv >= 0) {
      event.preventDefault();
      window.location.assign(optionen()[aktiv].href);
    } else if (event.key === "Escape" && !liste.hidden) {
      // nur die Liste schließen, nicht (wie sonst bei type=search) den Text löschen
      event.preventDefault();
      schliessen();
    }
  });
  // Liste bleibt beim Klick auf einen Treffer offen, bis der Link öffnet; sonst schließt sie beim Verlassen
  liste.addEventListener("mousedown", (event) => event.preventDefault());
  liste.addEventListener("mousemove", (event) => {
    const option = (event.target as Element).closest<HTMLAnchorElement>(".suchvorschlag");
    if (option) markieren(optionen().indexOf(option));
  });
  feld.addEventListener("blur", schliessen);
}
