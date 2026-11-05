import { useMemo, useState } from "react";
import { kurzDatum } from "../teamplaner/logik";
import { t } from "./texte";
import type { GAufgabe, GDaten } from "./typen";

/**
 * Vorgänger einer Aufgabe im Termine-Dialog: vorhandene als Karten, darunter Suche und
 * nach Projekt gruppierte Karten wie in der Palette des Teamplaners. Klick fügt hinzu.
 * Aufgaben, die schon nach dieser kommen, fehlen in der Auswahl (sonst Ringschluss).
 */
export function VorgaengerWahl({ aufgabe, daten, bearbeiten, onHinzufuegen, onEntfernen }: {
  aufgabe: GAufgabe;
  daten: GDaten;
  bearbeiten: boolean;
  onHinzufuegen: (vorher: number) => void;
  onEntfernen: (abhaengigkeitId: number) => void;
}) {
  const [suche, setSuche] = useState("");
  const vorgaenger = daten.abhaengigkeiten.filter((a) => a.nachher === aufgabe.id);
  const projektVon = (a: GAufgabe) =>
    daten.projekte.find((p) => p.id === a.projekt_id) ?? daten.externe_projekte[a.projekt_id];

  const gruppen = useMemo(() => {
    const nachfolger = alleNachfolger(aufgabe.id, daten);
    const begriff = suche.trim().toLowerCase();
    const kandidaten = Object.values(daten.aufgaben).filter((a) =>
      a.id !== aufgabe.id && !nachfolger.has(a.id) && !vorgaenger.some((v) => v.vorher === a.id)
      && (!begriff || `${a.titel} ${a.abschnitt} ${projektVon(a)?.name ?? ""}`.toLowerCase().includes(begriff)));
    const nachProjekt = new Map<number, GAufgabe[]>();
    for (const a of kandidaten) nachProjekt.set(a.projekt_id, [...(nachProjekt.get(a.projekt_id) ?? []), a]);
    return [...nachProjekt.entries()]
      .map(([pid, liste]) => ({
        projekt: daten.projekte.find((p) => p.id === pid) ?? daten.externe_projekte[pid],
        aufgaben: liste.sort((x, y) => Number(x.erledigt) - Number(y.erledigt)
          || (x.beginn ?? x.ende ?? "9999").localeCompare(y.beginn ?? y.ende ?? "9999") || x.titel.localeCompare(y.titel)),
      }))
      // Eigenes Projekt zuerst, dann alphabetisch
      .sort((x, y) => Number(y.projekt?.id === aufgabe.projekt_id) - Number(x.projekt?.id === aufgabe.projekt_id)
        || (x.projekt?.name ?? "").localeCompare(y.projekt?.name ?? ""));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [suche, daten, aufgabe.id]);

  return (
    <div className="stapel gt-vorgaenger">
      <h3>{t("vorgaenger")}</h3>
      {vorgaenger.length === 0 && <div className="gedaempft klein">{t("kein_vorgaenger")}</div>}
      {vorgaenger.length > 0 && (
        <div className="gt-wahl__liste gt-wahl__liste--gewaehlt">
          {vorgaenger.map((v) => {
            const a = daten.aufgaben[v.vorher];
            return a ? (
              <Karte key={v.id} aufgabe={a} projektName={projektVon(a)?.name} farbe={projektVon(a)?.farbe}>
                {bearbeiten && (
                  <button type="button" className="gt-wahl__x" aria-label={t("vorgaenger_entfernen", { titel: a.titel })}
                    title={t("entfernen")} onClick={() => onEntfernen(v.id)}>×</button>
                )}
              </Karte>
            ) : null;
          })}
        </div>
      )}
      {bearbeiten && (
        <>
          <label className="gt-wahl__suche">
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true"><circle cx="11" cy="11" r="7" /><path d="M20 20l-3.5-3.5" /></svg>
            <span className="sr-only">{t("vorgaenger_suchen")}</span>
            <input type="search" value={suche} placeholder={t("vorgaenger_suchen")} onChange={(ev) => setSuche(ev.target.value)} />
          </label>
          <div className="gt-wahl__liste" role="list" aria-label={t("vorgaenger_hinzufuegen")}>
            {gruppen.length === 0 && <div className="gedaempft klein gt-wahl__leer">{t("vorgaenger_keine_treffer")}</div>}
            {gruppen.map((g) => (
              <section key={g.projekt?.id ?? 0} className="gt-wahl__gruppe">
                <div className="gt-wahl__projekt">
                  <span className={`farbpunkt pf-${g.projekt?.farbe ?? "grau"}`} />{g.projekt?.name}
                  <span className="gt-wahl__anzahl">{g.aufgaben.length}</span>
                </div>
                {g.aufgaben.map((a) => (
                  <Karte key={a.id} aufgabe={a} farbe={g.projekt?.farbe} onKlick={() => { setSuche(""); onHinzufuegen(a.id); }} />
                ))}
              </section>
            ))}
          </div>
        </>
      )}
    </div>
  );
}

function Karte({ aufgabe, projektName, farbe, onKlick, children }: {
  aufgabe: GAufgabe;
  projektName?: string;
  farbe?: string;
  onKlick?: () => void;
  children?: React.ReactNode;
}) {
  const termin = aufgabe.beginn && aufgabe.ende ? `${kurzDatum(aufgabe.beginn)}–${kurzDatum(aufgabe.ende)}`
    : aufgabe.ende ? `${t("faellig")} ${kurzDatum(aufgabe.ende)}` : t("ohne_termin");
  const unter = [projektName, aufgabe.abschnitt, termin, aufgabe.erledigt ? t("erledigt") : ""].filter(Boolean).join(" · ");
  const inhalt = (
    <>
      <span className={`gt-wahl__titel${aufgabe.erledigt ? " gt-wahl__titel--erledigt" : ""}`}>{aufgabe.titel}</span>
      <span className="gt-wahl__unter">{unter}</span>
    </>
  );
  if (onKlick) {
    return (
      <button type="button" role="listitem" className={`gt-wahl__karte pf-${farbe ?? "grau"}`} onClick={onKlick}
        title={t("vorgaenger_klick")}>
        {inhalt}
        <span className="gt-wahl__plus" aria-hidden="true">+</span>
      </button>
    );
  }
  return <div className={`gt-wahl__karte gt-wahl__karte--fest pf-${farbe ?? "grau"}`}>{inhalt}{children}</div>;
}

/** Alle Aufgaben, die (auch indirekt) nach ``id`` kommen. */
function alleNachfolger(id: number, daten: GDaten) {
  const ergebnis = new Set<number>();
  const offen = [id];
  while (offen.length) {
    const aktuell = offen.pop()!;
    for (const a of daten.abhaengigkeiten) {
      if (a.vorher === aktuell && !ergebnis.has(a.nachher)) {
        ergebnis.add(a.nachher);
        offen.push(a.nachher);
      }
    }
  }
  return ergebnis;
}
