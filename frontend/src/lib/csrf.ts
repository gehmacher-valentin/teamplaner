/** CSRF-Token aus dem Meta-Tag der Seite (gesetzt in base.html). */
export function csrfToken(): string {
  return document.querySelector<HTMLMetaElement>('meta[name="csrf-token"]')?.content ?? "";
}

/** Sitzung beendet (z. B. Admin nach Inaktivität): ganze Seite zur Anmeldung, nichts mehr anzeigen. */
export function zurAnmeldung() {
  window.location.assign(`/anmelden/?next=${encodeURIComponent(window.location.pathname + window.location.search)}`);
}
