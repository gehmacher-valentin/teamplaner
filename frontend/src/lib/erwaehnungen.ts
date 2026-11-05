/**
 * @-Erwähnungen in Kommentarfeldern.
 *
 * <textarea data-erwaehnung-url="/personen/vorschlaege/"> zeigt beim Tippen von „@“
 * Vorschläge an. Gewählte Personen landen als {"Anzeigename": id} im versteckten Feld
 * name="erwaehnungen" desselben Formulars; der Server ersetzt sie durch @[id].
 */

interface Vorschlag {
  id: number;
  name: string;
  initialen: string;
  platzhalter: boolean;
  foto: string | null;
}

import { t } from "./texte";

const MUSTER = /(^|\s)@([^\s@][^@\n]{0,30})?$/u;

export function initErwaehnungen(wurzel: ParentNode) {
  wurzel.querySelectorAll<HTMLTextAreaElement>("textarea[data-erwaehnung-url]").forEach((feld) => {
    if (feld.dataset.erwaehnungAktiv) return;
    feld.dataset.erwaehnungAktiv = "1";
    einrichten(feld);
  });
}

function einrichten(feld: HTMLTextAreaElement) {
  const url = feld.dataset.erwaehnungUrl!;
  const versteckt = feld.form?.querySelector<HTMLInputElement>('input[name="erwaehnungen"]');
  const zuordnung: Record<string, number> = {};
  const liste = document.createElement("ul");
  liste.className = "vorschlaege";
  liste.setAttribute("role", "listbox");
  liste.hidden = true;
  feld.parentElement!.style.position = "relative";
  feld.insertAdjacentElement("afterend", liste);

  let vorschlaege: Vorschlag[] = [];
  let auswahl = 0;
  let timer: number | undefined;
  let anfrage = 0;

  const schliessen = () => {
    liste.hidden = true;
    vorschlaege = [];
  };

  const anzeigen = () => {
    liste.innerHTML = "";
    vorschlaege.forEach((v, i) => {
      const eintrag = document.createElement("li");
      eintrag.setAttribute("role", "option");
      eintrag.setAttribute("aria-selected", String(i === auswahl));
      const avatar = document.createElement(v.foto ? "img" : "span");
      avatar.className = "avatar avatar--klein" + (v.platzhalter ? " avatar--platzhalter" : ` av-${v.id % 8}`);
      if (v.foto) {
        avatar.className += " avatar--foto";
        (avatar as HTMLImageElement).src = v.foto;
        (avatar as HTMLImageElement).alt = "";
      } else {
        avatar.textContent = v.initialen;
      }
      eintrag.append(avatar, document.createTextNode(v.name + (v.platzhalter ? ` (${t("platzhalter")})` : "")));
      eintrag.addEventListener("mousedown", (e) => {
        e.preventDefault();
        uebernehmen(v);
      });
      liste.append(eintrag);
    });
    liste.style.top = `${feld.offsetTop + feld.offsetHeight + 2}px`;
    liste.style.left = `${feld.offsetLeft}px`;
    liste.hidden = vorschlaege.length === 0;
  };

  const uebernehmen = (v: Vorschlag) => {
    const davor = feld.value.slice(0, feld.selectionStart ?? feld.value.length);
    const danach = feld.value.slice(feld.selectionStart ?? feld.value.length);
    const treffer = davor.match(MUSTER);
    if (!treffer) return;
    const start = davor.length - (treffer[2]?.length ?? 0) - 1;
    const neu = davor.slice(0, start) + "@" + v.name + " ";
    feld.value = neu + danach;
    feld.setSelectionRange(neu.length, neu.length);
    zuordnung[v.name] = v.id;
    if (versteckt) versteckt.value = JSON.stringify(zuordnung);
    schliessen();
    feld.focus();
  };

  feld.addEventListener("input", () => {
    const davor = feld.value.slice(0, feld.selectionStart ?? feld.value.length);
    const treffer = davor.match(MUSTER);
    window.clearTimeout(timer);
    if (!treffer) {
      schliessen();
      return;
    }
    const suche = treffer[2] ?? "";
    timer = window.setTimeout(async () => {
      const nummer = ++anfrage;
      const antwort = await fetch(`${url}?q=${encodeURIComponent(suche)}`, { headers: { Accept: "application/json" } });
      if (!antwort.ok || nummer !== anfrage) return;
      vorschlaege = (await antwort.json()).personen as Vorschlag[];
      auswahl = 0;
      anzeigen();
    }, 120);
  });

  feld.addEventListener("keydown", (e) => {
    if (liste.hidden) return;
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      auswahl = (auswahl + (e.key === "ArrowDown" ? 1 : -1) + vorschlaege.length) % vorschlaege.length;
      anzeigen();
    } else if (e.key === "Enter" || e.key === "Tab") {
      e.preventDefault();
      uebernehmen(vorschlaege[auswahl]);
    } else if (e.key === "Escape") {
      schliessen();
    }
  });
  feld.addEventListener("blur", () => window.setTimeout(schliessen, 150));
}
