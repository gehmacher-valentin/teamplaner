import { useEffect, useRef, useState } from "react";
import { personenwahlEinrichten } from "../lib/personenwahl";
import { langDatum } from "./logik";
import { t } from "./texte";
import type { Aufgabe, Eintrag, Person } from "./typen";

/** Promise-basierter Bestätigungsdialog (z. B. Einteilung auf Feiertag). */
export function useBestaetigung() {
  const [offen, setOffen] = useState<{ text: string; ja: string; aufloesen: (ok: boolean) => void } | null>(null);
  const fragen = (text: string, ja = t("trotzdem_einteilen")) =>
    new Promise<boolean>((aufloesen) => setOffen({ text, ja, aufloesen }));
  const dialog = offen ? (
    <Modal titel={t("bitte_bestaetigen")} onSchliessen={() => { offen.aufloesen(false); setOffen(null); }}>
      <p style={{ margin: 0 }}>{offen.text}</p>
      <div className="formular__aktionen">
        <button type="button" className="knopf knopf--primaer" autoFocus
          onClick={() => { offen.aufloesen(true); setOffen(null); }}>{offen.ja}</button>
        <button type="button" className="knopf" onClick={() => { offen.aufloesen(false); setOffen(null); }}>{t("abbrechen")}</button>
      </div>
    </Modal>
  ) : null;
  return { fragen, dialog };
}

export function Modal({ titel, onSchliessen, children }: { titel: string; onSchliessen: () => void; children: React.ReactNode }) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const d = ref.current;
    if (d && !d.open) d.showModal();
    return () => d?.close();
  }, []);
  return (
    <dialog ref={ref} onCancel={(e) => { e.preventDefault(); onSchliessen(); }} aria-labelledby="tp-dialog-titel">
      <div className="dialog__inhalt">
        <h2 id="tp-dialog-titel">{titel}</h2>
        {children}
      </div>
    </dialog>
  );
}

interface BearbeitenProps {
  eintrag: Eintrag | null; // null = neu
  aufgabe?: Aufgabe;
  personen: Person[];
  vorgabePerson?: number;
  vorgabeDatum: string;
  onSpeichern: (werte: { person_id: number; von: string; bis: string }) => void;
  onLoeschen?: () => void;
  onSchliessen: () => void;
}

/** Einteilung/Abwesenheit per Formular bearbeiten oder anlegen – Alternative zum Ziehen. */
export function BearbeitenDialog({ eintrag, aufgabe, personen, vorgabePerson, vorgabeDatum, onSpeichern, onLoeschen, onSchliessen }: BearbeitenProps) {
  const [person, setPerson] = useState<number>(eintrag?.person_id ?? vorgabePerson ?? personen[0]?.id ?? 0);
  const [von, setVon] = useState(eintrag?.von ?? vorgabeDatum);
  const [bis, setBis] = useState(eintrag?.bis ?? vorgabeDatum);
  const [fehler, setFehler] = useState("");
  const titel = eintrag?.art === "abwesenheit" || (!eintrag && !aufgabe)
    ? (eintrag ? t("abwesenheit_bearbeiten") : t("abwesenheit_eintragen"))
    : (eintrag ? t("einteilung_bearbeiten") : t("aufgabe_einteilen"));

  const absenden = (e: React.FormEvent) => {
    e.preventDefault();
    if (!von || !bis) return setFehler(t("fehler_daten"));
    if (bis < von) return setFehler(t("fehler_reihenfolge"));
    if (!person) return setFehler(t("fehler_person"));
    onSpeichern({ person_id: person, von, bis });
  };

  return (
    <Modal titel={titel} onSchliessen={onSchliessen}>
      {aufgabe && (
        <a className="tp-dialog-aufgabe" href={aufgabe.url}>
          <span className="tp-dialog-aufgabe__text">
            {aufgabe.eltern && <span className="tp-dialog-aufgabe__eltern">{aufgabe.eltern}</span>}
            <strong>{aufgabe.titel}</strong>
          </span>
          <span className="tp-dialog-aufgabe__knopf">
            {t("aufgabe_oeffnen")}
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M5 12h14M13 6l6 6-6 6" /></svg>
          </span>
        </a>
      )}
      <form className="formular" onSubmit={absenden}>
        <label className="feld">
          {t("person")}
          <PersonenWahl personen={personen} wert={person} onWahl={setPerson} name={t("person")} />
        </label>
        <div className="formular__zeile">
          <label className="feld">
            {t("von")}
            <input type="date" value={von} onChange={(e) => { setVon(e.target.value); if (e.target.value > bis) setBis(e.target.value); }} required />
          </label>
          <label className="feld">
            {t("bis")}
            <input type="date" value={bis} min={von} onChange={(e) => setBis(e.target.value)} required />
          </label>
        </div>
        {von && bis && <div className="hilfetext">{von === bis ? langDatum(von) : t("von_bis", { von: langDatum(von), bis: langDatum(bis) })}</div>}
        {fehler && <div className="fehlerliste" role="alert">{fehler}</div>}
        <div className="formular__aktionen">
          <button type="submit" className="knopf knopf--primaer">{t("speichern")}</button>
          <button type="button" className="knopf" onClick={onSchliessen}>{t("abbrechen")}</button>
          <span className="luecke" />
          {onLoeschen && <button type="button" className="knopf knopf--gefahr" onClick={onLoeschen}>{t("entfernen")}</button>}
        </div>
      </form>
    </Modal>
  );
}

/**
 * Person wählen mit Tippsuche – dasselbe Bauteil wie in den Formularen (lib/personenwahl.ts). React
 * rendert nur die leere Hülle; Select und Textfeld darin legt das Bauteil selbst an.
 */
function PersonenWahl({ personen, wert, onWahl, name }: {
  personen: Person[]; wert: number; onWahl: (id: number) => void; name: string;
}) {
  const huelle = useRef<HTMLSpanElement>(null);
  const select = useRef<HTMLSelectElement | null>(null);
  const rueckruf = useRef(onWahl);
  rueckruf.current = onWahl;
  // Nur neu aufbauen, wenn sich die Personen wirklich ändern (nicht bei jedem neuen Array)
  const schluessel = personen.map((p) => `${p.id}:${p.name}:${p.platzhalter}`).join("|");
  useEffect(() => {
    const s = document.createElement("select");
    s.setAttribute("aria-label", name);
    for (const p of personen) s.add(new Option(`${p.name}${p.platzhalter ? t("platzhalter_zusatz") : ""}`, String(p.id)));
    s.value = String(wert);
    s.addEventListener("change", () => rueckruf.current(Number(s.value)));
    huelle.current!.replaceChildren(s);
    personenwahlEinrichten(s);
    select.current = s;
    return () => huelle.current?.replaceChildren();
    // Wert separat abgleichen, sonst würde jede Auswahl das Bauteil neu aufbauen
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [schluessel, name]);
  useEffect(() => {
    const s = select.current;
    if (s && s.value !== String(wert)) {
      s.value = String(wert);
      s.dispatchEvent(new Event("change"));
    }
  }, [wert]);
  return <span ref={huelle} className="personenwahl-huelle" />;
}
