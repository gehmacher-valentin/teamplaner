/**
 * Personenauswahl mit Tippsuche: Ein <select data-personenwahl> bekommt davor ein Textfeld,
 * in das man tippt; darunter erscheinen die passenden Personen. Das Select bleibt unsichtbar die Quelle
 * der Wahrheit, sodass Formulare, HTMX (hx-trigger="change") und data-auto-absenden unverändert
 * funktionieren. Die leere Option (z. B. „Nicht zugewiesen“) steht als Platzhaltertext im Feld.
 * Auch der Teamplaner nutzt das Bauteil (personenwahlEinrichten), damit es überall gleich arbeitet.
 */
import { t } from "./texte";

let zaehler = 0;

/** Kleinbuchstaben ohne Akzente – „Müller“ findet man mit „mul“ wie mit „mül“. */
export function normalisieren(text: string): string {
  return text.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();
}

/** Enthält ``text`` alle Wörter der ``suche`` (in beliebiger Reihenfolge)? */
export function passt(text: string, suche: string): boolean {
  const ziel = normalisieren(text);
  return normalisieren(suche).split(/\s+/).filter(Boolean).every((wort) => ziel.includes(wort));
}

export function initPersonenwahl(wurzel: ParentNode) {
  wurzel.querySelectorAll<HTMLSelectElement>("select[data-personenwahl]").forEach((s) => personenwahlEinrichten(s));
}

/** Name fürs Textfeld: aria-label des Selects oder der Text seines <label> (ohne Hilfe- und Fehlertexte). */
function beschriftung(select: HTMLSelectElement): string {
  const eigen = select.getAttribute("aria-label");
  if (eigen) return eigen;
  const label = select.labels?.[0];
  if (!label) return "";
  const kopie = label.cloneNode(true) as HTMLElement;
  kopie.querySelectorAll("select, .hilfetext, .fehlerliste, .personenwahl").forEach((el) => el.remove());
  return (kopie.textContent ?? "").replace(/\s+/g, " ").trim();
}

export function personenwahlEinrichten(select: HTMLSelectElement) {
  if (select.dataset.personenwahlFertig) return;
  select.dataset.personenwahlFertig = "1";
  const id = `personenwahl-${++zaehler}`;

  const huelle = document.createElement("div");
  huelle.className = "personenwahl";
  const eingabe = document.createElement("input");
  eingabe.type = "text";
  eingabe.className = `${select.className} personenwahl__eingabe`.trim();
  eingabe.autocomplete = "off";
  eingabe.spellcheck = false;
  eingabe.disabled = select.disabled;
  eingabe.setAttribute("role", "combobox");
  eingabe.setAttribute("aria-autocomplete", "list");
  eingabe.setAttribute("aria-expanded", "false");
  eingabe.setAttribute("aria-controls", `${id}-liste`);
  const name = beschriftung(select);
  if (name) eingabe.setAttribute("aria-label", name);
  const liste = document.createElement("ul");
  liste.className = "personenwahl__liste";
  liste.id = `${id}-liste`;
  liste.setAttribute("role", "listbox");
  if (name) liste.setAttribute("aria-label", name);
  liste.hidden = true;
  huelle.append(eingabe, liste);
  // Davor, damit ein umschließendes <label> das Textfeld fokussiert
  select.before(huelle);
  select.hidden = true;
  select.tabIndex = -1;

  let treffer: HTMLOptionElement[] = [];
  let aktiv = -1;
  let getippt = false;

  const leereOption = () => Array.from(select.options).find((o) => o.value === "");
  const anzeigen = () => {
    const gewaehlt = select.selectedOptions[0];
    eingabe.value = gewaehlt && gewaehlt.value !== "" ? gewaehlt.text : "";
    eingabe.placeholder = leereOption()?.text ?? t("person_suchen");
  };
  const zeichnen = () => {
    treffer = Array.from(select.options).filter((o) => !getippt || passt(o.text, eingabe.value));
    if (aktiv >= treffer.length) aktiv = treffer.length - 1;
    const eintraege = treffer.map((o, i) => {
      const li = document.createElement("li");
      li.id = `${id}-${i}`;
      li.setAttribute("role", "option");
      li.setAttribute("aria-selected", String(o.selected));
      li.dataset.index = String(i);
      li.textContent = o.text;
      li.className = ["personenwahl__option", o.value === "" ? "personenwahl__option--leer" : "",
        o.selected ? "personenwahl__option--gewaehlt" : "", i === aktiv ? "personenwahl__option--aktiv" : ""]
        .filter(Boolean).join(" ");
      return li;
    });
    if (!eintraege.length) {
      const leer = document.createElement("li");
      leer.className = "personenwahl__nichts";
      leer.textContent = t("keine_person");
      eintraege.push(leer);
    }
    liste.replaceChildren(...eintraege);
    if (aktiv >= 0) {
      eingabe.setAttribute("aria-activedescendant", `${id}-${aktiv}`);
      const li = eintraege[aktiv]; // markierte Person im sichtbaren Bereich der Liste halten
      if (li.offsetTop < liste.scrollTop) liste.scrollTop = li.offsetTop;
      else if (li.offsetTop + li.offsetHeight > liste.scrollTop + liste.clientHeight) {
        liste.scrollTop = li.offsetTop + li.offsetHeight - liste.clientHeight;
      }
    } else {
      eingabe.removeAttribute("aria-activedescendant");
    }
  };
  // Fest positioniert, damit Listen mit overflow (Tabellen, Dialoge) die Auswahl nicht abschneiden
  const position = () => {
    const r = eingabe.getBoundingClientRect();
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
  const oeffnen = () => {
    if (eingabe.disabled || !liste.hidden) return;
    liste.hidden = false;
    eingabe.setAttribute("aria-expanded", "true");
    position();
    zeichnen();
    window.addEventListener("scroll", position, true);
    window.addEventListener("resize", position);
  };
  const schliessen = () => {
    liste.hidden = true;
    getippt = false;
    eingabe.setAttribute("aria-expanded", "false");
    eingabe.removeAttribute("aria-activedescendant");
    window.removeEventListener("scroll", position, true);
    window.removeEventListener("resize", position);
  };
  const waehlen = (option: HTMLOptionElement) => {
    schliessen();
    if (select.value !== option.value) {
      select.value = option.value;
      select.dispatchEvent(new Event("change", { bubbles: true }));
    }
    anzeigen();
  };

  eingabe.addEventListener("focus", () => {
    aktiv = Math.max(0, select.selectedIndex);
    oeffnen();
    eingabe.select();
  });
  eingabe.addEventListener("click", oeffnen);
  eingabe.addEventListener("input", () => {
    getippt = true;
    aktiv = 0;
    if (liste.hidden) oeffnen();
    else zeichnen();
  });
  eingabe.addEventListener("keydown", (ev) => {
    if (ev.key === "ArrowDown" || ev.key === "ArrowUp") {
      ev.preventDefault();
      if (liste.hidden) oeffnen();
      aktiv = Math.min(Math.max(aktiv + (ev.key === "ArrowDown" ? 1 : -1), 0), treffer.length - 1);
      zeichnen();
    } else if (ev.key === "Enter") {
      ev.preventDefault(); // nicht das Formular absenden
      if (!liste.hidden && treffer[aktiv]) waehlen(treffer[aktiv]);
    } else if (ev.key === "Escape" && !liste.hidden) {
      ev.preventDefault();
      ev.stopPropagation(); // einen umgebenden Dialog offen lassen
      schliessen();
      anzeigen();
    } else if (ev.key === "Tab" && !liste.hidden && getippt && treffer[aktiv]) {
      waehlen(treffer[aktiv]);
    }
  });
  eingabe.addEventListener("blur", () => {
    if (liste.hidden) return;
    const text = normalisieren(eingabe.value.trim());
    const gleich = getippt && Array.from(select.options).find((o) => normalisieren(o.text) === text);
    if (gleich) waehlen(gleich);
    else if (getippt && !text && leereOption()) waehlen(leereOption()!);
    else {
      schliessen();
      anzeigen();
    }
  });
  // Das Textfeld selbst löst keine Formular-Aktion aus, nur das Select
  eingabe.addEventListener("change", (ev) => ev.stopPropagation());
  liste.addEventListener("mousedown", (ev) => ev.preventDefault()); // Fokus im Textfeld lassen
  liste.addEventListener("click", (ev) => {
    const li = (ev.target as HTMLElement).closest<HTMLElement>("[data-index]");
    if (li) waehlen(treffer[Number(li.dataset.index)]);
  });
  select.addEventListener("change", anzeigen);
  select.form?.addEventListener("reset", () => window.setTimeout(anzeigen));
  anzeigen();
}
