import { useDraggable } from "@dnd-kit/core";
import { kurzDatum, personentageText } from "./logik";
import { t } from "./texte";
import type { Aufgabe, PaletteDaten, Projekt } from "./typen";

interface Props {
  daten: PaletteDaten | null;
  heute: string;
  modus: "offen" | "projekt";
  projektId: number | null;
  suche: string;
  projekte: Projekt[];
  onModus: (modus: "offen" | "projekt") => void;
  onProjekt: (id: number | null) => void;
  onSuche: (text: string) => void;
  onEinteilen: (aufgabe: Aufgabe) => void;
  onAbwesenheit: () => void;
}

export function Palette({ daten, heute, modus, projektId, suche, projekte, onModus, onProjekt, onSuche, onEinteilen, onAbwesenheit }: Props) {
  const aufgaben = daten?.aufgaben ?? [];
  return (
    <aside className="tp-palette karte" aria-label={t("einteilen")}>
      <div className="tp-palette__abschnitt">
        <h2>{t("abwesenheit")}</h2>
        <AbwesenheitChip onAbwesenheit={onAbwesenheit} />
      </div>
      <div className="tp-palette__abschnitt">
        <div className="zeile">
          <h2 style={{ flex: 1 }}>{t("aufgaben_zum_einteilen")}</h2>
          <span className="zaehler">{aufgaben.length}</span>
        </div>
        <div className="knopfgruppe" role="group" aria-label={t("quelle")}>
          <button type="button" aria-pressed={modus === "offen"} onClick={() => onModus("offen")}>{t("nicht_eingeteilt")}</button>
          <button type="button" aria-pressed={modus === "projekt"} onClick={() => onModus("projekt")}>{t("projektliste")}</button>
        </div>
        {modus === "projekt" && (
          <label className="feld">
            <span className="sr-only">{t("projekt")}</span>
            <select value={projektId ?? ""} onChange={(e) => onProjekt(e.target.value ? Number(e.target.value) : null)}>
              <option value="">{t("projekt_waehlen")}</option>
              {projekte.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
            </select>
          </label>
        )}
        <label className="tp-filter">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#5B625E" strokeWidth="2" aria-hidden="true"><circle cx="11" cy="11" r="7" /><path d="M20 20l-3.5-3.5" /></svg>
          <span className="sr-only">{t("aufgaben_filtern")}</span>
          <input type="search" placeholder={t("filtern")} value={suche} onChange={(e) => onSuche(e.target.value)} />
        </label>
      </div>
      <div className="tp-palette__liste">
        {daten === null && <div className="leer">{t("laedt")}</div>}
        {daten !== null && aufgaben.length === 0 && (
          <div className="leer">{modus === "projekt" && !projektId ? t("bitte_projekt") : t("keine_aufgaben")}</div>
        )}
        {aufgaben.map((a) => (
          <Karte key={a.id} aufgabe={a} projekt={daten?.projekte[a.projekt_id]} heute={heute} onEinteilen={onEinteilen} />
        ))}
      </div>
    </aside>
  );
}

function AbwesenheitChip({ onAbwesenheit }: { onAbwesenheit: () => void }) {
  const { attributes, listeners, setNodeRef, isDragging } = useDraggable({ id: "abwesenheit-neu", data: { typ: "neu-abwesenheit" } });
  return (
    <div className="zeile">
      <div ref={setNodeRef} {...attributes} {...listeners} className={`tp-abwesend-chip${isDragging ? " tp-balken--zieht" : ""}`}
        role="button" aria-label={t("abwesend_ziehen")}>{t("abwesend")}</div>
      <button type="button" className="knopf knopf--klein" onClick={onAbwesenheit}>{t("eintragen")}</button>
    </div>
  );
}

function Karte({ aufgabe, projekt, heute, onEinteilen }: { aufgabe: Aufgabe; projekt?: Projekt; heute: string; onEinteilen: (a: Aufgabe) => void }) {
  const { attributes, listeners, setNodeRef, isDragging } = useDraggable({
    id: `aufgabe:${aufgabe.id}`,
    data: { typ: "neu-einteilung", aufgabe, projekt },
  });
  const anteil = aufgabe.schaetzung ? Math.min(100, Math.round((aufgabe.eingeteilt / aufgabe.schaetzung) * 100)) : 0;
  const ueberfaellig = aufgabe.faellig_am !== null && aufgabe.faellig_am < heute;
  return (
    <div className={`tp-karte pf-${projekt?.farbe ?? "grau"}${isDragging ? " tp-balken--zieht" : ""}`}>
      <div ref={setNodeRef} {...attributes} {...listeners} className="tp-karte__ziehen" role="button"
        aria-label={t("karte_ziehen", { titel: aufgabe.titel })}>
        <svg width="14" height="18" viewBox="0 0 14 18" fill="#8E958F" aria-hidden="true"><circle cx="4" cy="4" r="1.5" /><circle cx="10" cy="4" r="1.5" /><circle cx="4" cy="9" r="1.5" /><circle cx="10" cy="9" r="1.5" /><circle cx="4" cy="14" r="1.5" /><circle cx="10" cy="14" r="1.5" /></svg>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div className="tp-karte__titel">{aufgabe.titel}</div>
          <div className="gedaempft" style={{ fontSize: 12 }}>{aufgabe.eltern ? `↳ ${aufgabe.eltern} · ` : ""}{projekt?.name}</div>
        </div>
      </div>
      <div className="tp-karte__fortschritt">
        <div className="tp-karte__balken"><div style={{ width: `${anteil}%` }} /></div>
        <span className="mono">{personentageText(aufgabe.eingeteilt, aufgabe.schaetzung)}</span>
      </div>
      <div className="tp-karte__fuss">
        {aufgabe.gewerk && <span className="tag">{aufgabe.gewerk}</span>}
        <span className={`tag${ueberfaellig ? " badge--warn" : ""}`}>
          {aufgabe.faellig_am ? t("faellig", { datum: kurzDatum(aufgabe.faellig_am) }) : t("ohne_termin")}
        </span>
        <span className="luecke" />
        <a href={aufgabe.url} className="klein">{t("oeffnen")}</a>
        <button type="button" className="knopf knopf--text klein" onClick={() => onEinteilen(aufgabe)}>{t("einteilen_dialog")}</button>
      </div>
    </div>
  );
}
