/**
 * Restzeit der Admin-Sitzung in der Kopfzeile: Admins werden nach einer Stunde ohne eigene
 * Aktivität abgemeldet (kern.middleware.SitzungMiddleware). Der Knopf zeigt, wie lange noch, und ein Klick
 * setzt die Frist zurück (POST zählt als Aktivität). Jede Antwort an Admins trägt das Fristende in
 * X-Sitzung-Ablauf; so gleicht sich die Anzeige mit jeder HTMX-Antwort ab – auch mit der Glocke, die
 * jede Minute nachfragt, wenn in einem anderen Tab gearbeitet wurde. Läuft die Zeit ab, fragt die Seite
 * im Hintergrund nach und springt zur Anmeldung, falls die Sitzung wirklich beendet ist.
 */
import { csrfToken, zurAnmeldung } from "./csrf";
import { toast } from "./toast";
import { t } from "./texte";

const KNAPP_SEKUNDEN = 5 * 60;

/** „47 min“; in den letzten fünf Minuten sekundengenau „4:05“. */
export function restzeit(sekunden: number): string {
  const s = Math.max(0, Math.floor(sekunden));
  if (s > KNAPP_SEKUNDEN) return `${Math.ceil(s / 60)} min`;
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

export function initSitzungsfrist() {
  const knopf = document.querySelector<HTMLButtonElement>("[data-sitzungsfrist]");
  if (!knopf) return;
  const anzeige = knopf.querySelector<HTMLElement>("[data-frist-zeit]")!;
  const url = knopf.dataset.url!;
  let ablauf = Number(knopf.dataset.ablauf) * 1000;
  // Serveruhr minus eigene Uhr: eine falsch gehende Uhr am Rechner verschiebt die Anzeige nicht
  let versatz = Number(knopf.dataset.jetzt) * 1000 - Date.now();
  let naechstePruefung = 0;

  const uebernehmen = (ablaufKopf: string | null, jetztKopf: string | null) => {
    if (!ablaufKopf) return;
    ablauf = Number(ablaufKopf) * 1000;
    if (jetztKopf) versatz = Number(jetztKopf) * 1000 - Date.now();
    zeichnen();
  };
  const pruefen = async () => {
    try {
      const antwort = await fetch(url, { headers: { "X-Hintergrund": "1" }, credentials: "same-origin" });
      if (antwort.redirected || antwort.status === 401 || antwort.status === 403) return zurAnmeldung();
      uebernehmen(antwort.headers.get("X-Sitzung-Ablauf"), antwort.headers.get("X-Sitzung-Jetzt"));
    } catch {
      // Netz weg: beim nächsten Mal
    }
  };
  const zeichnen = () => {
    const rest = (ablauf - (Date.now() + versatz)) / 1000;
    anzeige.textContent = restzeit(rest);
    knopf.classList.toggle("kopf__frist--knapp", rest <= KNAPP_SEKUNDEN);
    if (rest <= 0 && Date.now() >= naechstePruefung) {
      naechstePruefung = Date.now() + 5000;
      void pruefen();
    }
  };

  knopf.addEventListener("click", async () => {
    knopf.disabled = true;
    try {
      const antwort = await fetch(url, {
        method: "POST", headers: { "X-CSRFToken": csrfToken() }, credentials: "same-origin",
      });
      if (antwort.redirected || antwort.status === 401 || antwort.status === 403) return zurAnmeldung();
      if (!antwort.ok) throw new Error(String(antwort.status));
      uebernehmen(antwort.headers.get("X-Sitzung-Ablauf"), antwort.headers.get("X-Sitzung-Jetzt"));
    } catch {
      toast(t("speichern_fehlgeschlagen"), { art: "fehler" });
    } finally {
      knopf.disabled = false;
    }
  });
  document.addEventListener("htmx:afterRequest", (event) => {
    const xhr = (event as CustomEvent).detail?.xhr as XMLHttpRequest | undefined;
    if (xhr) uebernehmen(xhr.getResponseHeader("X-Sitzung-Ablauf"), xhr.getResponseHeader("X-Sitzung-Jetzt"));
  });
  zeichnen();
  window.setInterval(zeichnen, 1000);
}
