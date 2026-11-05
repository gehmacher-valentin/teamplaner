import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { toast } from "../lib/toast";
import { Modal, useBestaetigung } from "../teamplaner/Dialoge";
import { useGespeichert } from "../teamplaner/hooks";
import { kalenderwoche, kurzDatum, langDatum, plusTage, wochentag } from "../teamplaner/logik";
import { api, GanttFehler } from "./api";
import {
  balken,
  MASSSTAB,
  monate,
  pfad,
  pfeile,
  projektZeitraum,
  tageZwischen,
  verschieben,
  x,
  ZEILE,
  zeilen,
  type Massstab,
} from "./logik";
import { t } from "./texte";
import { VorgaengerWahl } from "./VorgaengerWahl";
import type { GAufgabe, GDaten, GOptionen, GProjekt } from "./typen";

const LINKS = 320;

interface Einstellungen {
  ansicht: number;
  massstab: Massstab;
  pfeile: boolean;
  erledigte: boolean;
  zugeklappt: number[];
}

/** ``tage``: beim Verschieben einer Sammelaufgabe wandern die Unteraufgaben in der Vorschau mit. */
type Vorschau = { art: "aufgabe" | "projekt"; id: number; beginn: string | null; ende: string | null; tage?: number };
type Dialog = { art: "aufgabe"; aufgabe: GAufgabe } | { art: "projekt"; projekt: GProjekt };

export function Gantt() {
  const [e, setE] = useGespeichert<Einstellungen>("gantt-einstellungen", {
    ansicht: 0, massstab: "monat", pfeile: true, erledigte: true, zugeklappt: [],
  });
  // Unteraufgaben standardmäßig aufgeklappt (sonst eingeklappt): Einstellung am Konto, nicht im Browser
  const [unterAuf, setUnterAuf] = useState(false);
  // Hauptaufgaben, die vom Standard (e.unterAuf) abweichend auf- bzw. zugeklappt sind – nur bis zum Neuladen
  const [umgeschaltet, setUmgeschaltet] = useState<Set<number>>(() => new Set());
  const [optionen, setOptionen] = useState<GOptionen | null>(null);
  const [daten, setDaten] = useState<GDaten | null>(null);
  const [vorschau, setVorschau] = useState<Vorschau | null>(null);
  const [verbinden, setVerbinden] = useState<{ von: number; x1: number; y1: number; x2: number; y2: number } | null>(null);
  const [dialog, setDialog] = useState<Dialog | null>(null);
  const [neuesProjekt, setNeuesProjekt] = useState("");
  const [einstellungenOffen, setEinstellungenOffen] = useState(false);
  const bestaetigung = useBestaetigung();
  const rahmen = useRef<HTMLDivElement>(null);
  const koerper = useRef<HTMLDivElement>(null);
  const gescrollt = useRef<number | null>(null);

  const ansichtId = optionen?.ansichten.find((a) => a.id === e.ansicht)?.id ?? optionen?.ansichten[0]?.id;
  const px = MASSSTAB[e.massstab];
  const bearbeiten = daten?.ansicht.recht === "bearbeiten";
  const zugeklappt = useMemo(() => new Set(e.zugeklappt), [e.zugeklappt]);

  const zeige = (text: string) => toast(text, { art: "fehler" }); // als Toast, damit nichts springt

  useEffect(() => {
    api.optionen().then((o) => {
      setOptionen(o);
      setUnterAuf(o.unteraufgaben_offen);
    }).catch((f) => zeige(f.message));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const unterAufAendern = (wert: boolean) => {
    setUmgeschaltet(new Set());
    setUnterAuf(wert);
    api.unteraufgabenOffen(wert).catch((f) => {
      setUnterAuf(!wert);
      zeige(f instanceof Error ? f.message : t("speichern_fehler"));
    });
  };

  const laden = useCallback(async () => {
    if (!ansichtId) return;
    try {
      setDaten(await api.daten(ansichtId));
    } catch (f) {
      zeige(f instanceof Error ? f.message : t("speichern_fehler"));
    }
  }, [ansichtId]);
  useEffect(() => {
    laden();
  }, [laden]);

  const liste = useMemo(
    () => (daten ? zeilen(daten, zugeklappt, e.erledigte, (id) => unterAuf !== umgeschaltet.has(id)) : []),
    [daten, zugeklappt, e.erledigte, unterAuf, umgeschaltet],
  );
  const unterUmschalten = (id: number) =>
    setUmgeschaltet((alt) => {
      const neu = new Set(alt);
      if (!neu.delete(id)) neu.add(id);
      return neu;
    });
  const start = daten?.von ?? "";
  const breite = daten ? (tageZwischen(daten.von, daten.bis) + 1) * px : 0;
  const pfeilListe = useMemo(() => (daten && e.pfeile ? pfeile(daten, liste, start, px) : []), [daten, liste, start, px, e.pfeile]);

  // Beim ersten Anzeigen und bei Maßstabswechsel zu „heute“ scrollen
  useLayoutEffect(() => {
    if (!daten || !rahmen.current || gescrollt.current === px) return;
    gescrollt.current = px;
    rahmen.current.scrollLeft = Math.max(0, x(daten.heute, start, px) - 200);
  }, [daten, px, start]);

  // ---------- Speichern ----------
  const speichern = async (aktion: () => Promise<unknown>) => {
    try {
      await aktion();
    } catch (f) {
      zeige(f instanceof GanttFehler || f instanceof Error ? f.message : t("speichern_fehler"));
    } finally {
      setVorschau(null);
      laden();
    }
  };

  const aufgabeTermine = (a: GAufgabe, beginn: string | null, ende: string | null) =>
    speichern(async () => {
      setDaten((d) => (d ? { ...d, aufgaben: { ...d.aufgaben, [a.id]: { ...a, beginn, ende } } } : d));
      await api.aufgabe(ansichtId!, a.id, { beginn, ende, version: a.version });
    });

  const projektTermine = (p: GProjekt, beginn: string | null, ende: string | null) =>
    speichern(async () => {
      setDaten((d) => (d ? { ...d, projekte: d.projekte.map((x2) => (x2.id === p.id ? { ...p, beginn, ende } : x2)) } : d));
      await api.projekt(ansichtId!, p.id, { beginn, ende });
    });

  const abhaengigkeitAnlegen = (vorher: number, nachher: number) =>
    speichern(() => api.abhaengigkeitAnlegen(ansichtId!, vorher, nachher));

  const abhaengigkeitLoeschen = async (id: number) => {
    const abh = daten?.abhaengigkeiten.find((a) => a.id === id);
    if (!abh || !daten) return;
    const ok = await bestaetigung.fragen(
      t("abh_loeschen_frage", { a: daten.aufgaben[abh.vorher].titel, b: daten.aufgaben[abh.nachher].titel }),
      t("entfernen"),
    );
    if (ok) speichern(() => api.abhaengigkeitLoeschen(ansichtId!, id));
  };

  const projektZuordnen = async (projekt: { id: number; name: string }, hinzu: boolean) => {
    if (!hinzu && !(await bestaetigung.fragen(t("projekt_entfernen_frage", { name: projekt.name }), t("entfernen")))) return;
    speichern(() => api.projektZuordnen(ansichtId!, projekt.id, hinzu));
  };

  // ---------- Ziehen ----------
  const ziehen = (
    ev: React.PointerEvent,
    art: "mitte" | "links" | "rechts",
    ziel: Vorschau,
    fertig: (beginn: string | null, ende: string | null) => void,
    klick: () => void,
  ) => {
    ev.preventDefault();
    ev.stopPropagation();
    (ev.currentTarget as HTMLElement).setPointerCapture?.(ev.pointerId);
    const x0 = ev.clientX;
    let neu = ziel;
    let bewegt = false;
    const bewegen = (pe: PointerEvent) => {
      const tage = Math.round((pe.clientX - x0) / px);
      if (Math.abs(pe.clientX - x0) > 3) bewegt = true;
      let { beginn, ende } = ziel;
      if (art === "mitte") {
        beginn = verschieben(beginn, tage);
        ende = verschieben(ende, tage);
        neu = { ...ziel, beginn, ende, tage };
        setVorschau(neu);
        return;
      } else if (art === "links" && beginn) {
        beginn = verschieben(beginn, tage);
        if (ende && beginn! > ende) beginn = ende;
      } else if (art === "rechts" && ende) {
        ende = verschieben(ende, tage);
        if (beginn && ende! < beginn) ende = beginn;
      }
      neu = { ...ziel, beginn, ende };
      setVorschau(neu);
    };
    const los = () => {
      window.removeEventListener("pointermove", bewegen);
      window.removeEventListener("pointerup", los);
      if (!bewegt) {
        setVorschau(null);
        klick();
        return;
      }
      if (neu.beginn === ziel.beginn && neu.ende === ziel.ende) {
        setVorschau(null);
        return;
      }
      fertig(neu.beginn, neu.ende);
    };
    window.addEventListener("pointermove", bewegen);
    window.addEventListener("pointerup", los);
  };

  /** Neue Termine durch Ziehen in einer leeren Zeile (Aufgabe ohne Termine). */
  const aufziehen = (ev: React.PointerEvent, a: GAufgabe) => {
    if (!bearbeiten || a.extern || a.beginn || a.ende) return;
    const flaeche = (ev.currentTarget as HTMLElement).getBoundingClientRect();
    const tag = (clientX: number) => plusTage(start, Math.floor((clientX - flaeche.left) / px));
    const anfang = tag(ev.clientX);
    let ende = anfang;
    setVorschau({ art: "aufgabe", id: a.id, beginn: anfang, ende });
    const bewegen = (pe: PointerEvent) => {
      ende = tag(pe.clientX);
      setVorschau({ art: "aufgabe", id: a.id, beginn: anfang < ende ? anfang : ende, ende: anfang < ende ? ende : anfang });
    };
    const los = () => {
      window.removeEventListener("pointermove", bewegen);
      window.removeEventListener("pointerup", los);
      aufgabeTermine(a, anfang < ende ? anfang : ende, anfang < ende ? ende : anfang);
    };
    window.addEventListener("pointermove", bewegen);
    window.addEventListener("pointerup", los);
  };

  /** Vom Punkt am Balkenende auf eine andere Aufgabe ziehen: „A vor B“. */
  const verbindenStart = (ev: React.PointerEvent, a: GAufgabe, zeile: number, sx: number) => {
    ev.preventDefault();
    ev.stopPropagation();
    (ev.currentTarget as HTMLElement).setPointerCapture?.(ev.pointerId);
    const box = koerper.current!.getBoundingClientRect();
    const y1 = zeile * ZEILE + ZEILE / 2;
    setVerbinden({ von: a.id, x1: sx, y1, x2: sx, y2: y1 });
    const bewegen = (pe: PointerEvent) =>
      setVerbinden((v) => (v ? { ...v, x2: pe.clientX - box.left - LINKS, y2: pe.clientY - box.top } : v));
    const los = (pe: PointerEvent) => {
      window.removeEventListener("pointermove", bewegen);
      window.removeEventListener("pointerup", los);
      setVerbinden(null);
      const ziel = document.elementFromPoint(pe.clientX, pe.clientY)?.closest<HTMLElement>("[data-aufgabe]");
      const nachher = ziel ? Number(ziel.dataset.aufgabe) : NaN;
      if (nachher && nachher !== a.id) abhaengigkeitAnlegen(a.id, nachher);
    };
    window.addEventListener("pointermove", bewegen);
    window.addEventListener("pointerup", los);
  };

  // ---------- Darstellung ----------
  if (optionen && optionen.ansichten.length === 0) {
    return (
      <div className="gt">
        <h1>{t("titel")}</h1>
        <div className="karte leer">{t("keine_ansichten")}</div>
        {optionen.darf_verwalten && <a className="knopf" href="/einstellungen/ansichten/?art=gantt">{t("ansichten_verwalten")}</a>}
      </div>
    );
  }

  const zuordenbar = optionen?.projekte.filter((p) => !daten?.projekte.some((x2) => x2.id === p.id)) ?? [];
  const wochenendeVersatz = daten ? (((5 - wochentag(daten.von)) % 7) + 7) % 7 : 0;

  const ansichtName = optionen?.ansichten.find((a) => a.id === ansichtId)?.name;

  return (
    <div className="gt">
      <div className="seitenkopf">
        <div className="seitenkopf__titel">
          <h1>{t("titel")}</h1>
          {ansichtName && <div className="nur-drucken">{ansichtName}</div>}
        </div>
      </div>

      <div className="tp-werkzeuge nicht-drucken">
        <div className="knopfgruppe" role="group" aria-label={t("zoom")}>
          {(Object.keys(MASSSTAB) as Massstab[]).map((m) => (
            <button key={m} type="button" aria-pressed={e.massstab === m} onClick={() => setE({ massstab: m })}>{t(m)}</button>
          ))}
        </div>
        <button type="button" className="knopf" onClick={() => {
          if (rahmen.current && daten) rahmen.current.scrollLeft = Math.max(0, x(daten.heute, start, px) - 200);
        }}>{t("heute")}</button>
        <span className="luecke" />
        <button type="button" className="knopf tp-filter-knopf" aria-expanded={einstellungenOffen} aria-controls="gt-einstellungen"
          onClick={() => setEinstellungenOffen(!einstellungenOffen)}>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true"><path d="M4 6h10M18 6h2M4 12h4M12 12h8M4 18h12M20 18h0" /><circle cx="16" cy="6" r="2" /><circle cx="10" cy="12" r="2" /><circle cx="18" cy="18" r="2" /></svg>
          {t("einstellungen")}
        </button>
        {/* Ansicht ganz rechts, ohne sichtbare Beschriftung */}
        {optionen && (
          <label className="feld tp-ansichtwahl">
            <span className="sr-only">{t("ansicht")}</span>
            <select value={ansichtId ?? ""} onChange={(ev) => { gescrollt.current = null; setE({ ansicht: Number(ev.target.value) }); }}>
              {optionen.ansichten.map((a) => (
                <option key={a.id} value={a.id}>{a.name}{a.recht === "sehen" ? t("nur_sehen") : ""}</option>
              ))}
            </select>
          </label>
        )}
        <div id="gt-einstellungen" className={`tp-filter-optionen${einstellungenOffen ? " offen" : ""}`}>
        <label className="feld feld--zeile"><input type="checkbox" checked={e.pfeile} onChange={(ev) => setE({ pfeile: ev.target.checked })} />{t("abhaengigkeiten")}</label>
        <label className="feld feld--zeile"><input type="checkbox" checked={e.erledigte} onChange={(ev) => setE({ erledigte: ev.target.checked })} />{t("erledigte")}</label>
        <label className="feld feld--zeile"><input type="checkbox" checked={unterAuf} onChange={(ev) => unterAufAendern(ev.target.checked)} />{t("unter_aufgeklappt")}</label>
        <button type="button" className="knopf" onClick={() => setE({ zugeklappt: daten?.projekte.map((p) => p.id) ?? [] })}>{t("alle_zu")}</button>
        <button type="button" className="knopf" onClick={() => setE({ zugeklappt: [] })}>{t("alle_auf")}</button>
        {optionen?.darf_verwalten && zuordenbar.length > 0 && (
          <div className="zeile">
            <label className="sr-only" htmlFor="gt-neu">{t("projekt_hinzufuegen")}</label>
            <select id="gt-neu" value={neuesProjekt} onChange={(ev) => setNeuesProjekt(ev.target.value)}>
              <option value="">{t("projekt_hinzufuegen")}</option>
              {zuordenbar.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
            </select>
            <button type="button" className="knopf" disabled={!neuesProjekt} onClick={() => {
              const p = zuordenbar.find((x2) => String(x2.id) === neuesProjekt);
              if (p) projektZuordnen(p, true);
              setNeuesProjekt("");
            }}>{t("hinzufuegen")}</button>
          </div>
        )}
        {optionen?.darf_verwalten && <a className="knopf" href="/einstellungen/ansichten/?art=gantt">{t("ansichten_verwalten")}</a>}
        </div>
      </div>


      {!daten ? (
        <div className="karte leer">{t("laedt")}</div>
      ) : daten.projekte.length === 0 ? (
        <div className="karte leer">{t("leer")}</div>
      ) : (
        <div className="gt-rahmen karte" ref={rahmen}>
          <div className="gt-inner" style={{ width: LINKS + breite }}>
            <div className="gt-kopf">
              <div className="gt-links gt-links--kopf">{t("aufgaben")}</div>
              <div className="gt-achse" style={{ width: breite }}>
                <div className="gt-monate">
                  {monate(daten.von, daten.bis).map((m) => (
                    <div key={m.beginn} style={{ width: m.tage * px }} className="gt-monat">
                      {m.tage * px > 60 ? new Date(`${m.beginn}T00:00:00`).toLocaleDateString(document.documentElement.lang || "de", { month: e.massstab === "quartal" ? "short" : "long", year: "numeric" }) : ""}
                    </div>
                  ))}
                </div>
                <div className="gt-ticks">
                  {e.massstab !== "quartal" && Array.from({ length: tageZwischen(daten.von, daten.bis) + 1 }, (_, i) => plusTage(daten.von, i))
                    .filter((d) => (e.massstab === "woche" ? true : wochentag(d) === 0))
                    .map((d) => (
                      <div key={d} className={`gt-tick${d === daten.heute ? " gt-tick--heute" : ""}`} style={{ left: x(d, start, px), width: e.massstab === "woche" ? px : 7 * px }}>
                        {e.massstab === "woche" ? d.slice(8) : t("kw", { n: kalenderwoche(d) })}
                      </div>
                    ))}
                </div>
              </div>
            </div>

            <div className="gt-koerper" ref={koerper} style={{ height: liste.length * ZEILE }}>
              <div className="gt-hintergrund" style={{
                left: LINKS, width: breite,
                backgroundImage: e.massstab === "quartal" ? undefined
                  : `repeating-linear-gradient(to right, transparent 0 ${5 * px}px, var(--gt-wochenende) ${5 * px}px ${7 * px}px)`,
                backgroundPositionX: `${(wochenendeVersatz - 5) * px}px`,
              }}>
                {Object.entries(daten.frei).map(([d, name]) => (
                  <div key={d} className="gt-frei" title={name} style={{ left: x(d, start, px), width: px }} />
                ))}
                <div className="gt-heute" style={{ left: x(daten.heute, start, px) + px / 2 }} />
              </div>

              {liste.map((z, i) => {
                if (z.art === "extern") {
                  return <div key="extern" className="gt-zeile gt-zeile--gruppe"><div className="gt-links">{t("extern")}</div><div className="gt-zeit" /></div>;
                }
                if (z.art === "projekt") {
                  const p = z.projekt;
                  const v = vorschau?.art === "projekt" && vorschau.id === p.id ? vorschau : null;
                  const beginn = v ? v.beginn : p.beginn;
                  const ende = v ? v.ende : p.ende;
                  // Reichen Aufgaben über Beginn/Ende hinaus, wächst der Balken mit; der Überzug ist markiert
                  const zr = projektZeitraum({ beginn, ende, plan_von: p.plan_von, plan_bis: p.plan_bis });
                  const ueberzug = zr.vorne || zr.hinten
                    ? t("ueberzug", { von: beginn ? langDatum(beginn) : "–", bis: ende ? langDatum(ende) : "–" }) : "";
                  return (
                    <div key={`p${p.id}`} className={`gt-zeile gt-zeile--projekt pf-${p.farbe}`}>
                      <div className="gt-links">
                        <button type="button" className="gt-klapp" aria-expanded={!z.zu}
                          aria-label={t(z.zu ? "ausklappen" : "einklappen", { name: p.name })}
                          onClick={() => setE({ zugeklappt: z.zu ? e.zugeklappt.filter((id) => id !== p.id) : [...e.zugeklappt, p.id] })}>
                          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.6" aria-hidden="true" style={{ transform: z.zu ? "rotate(-90deg)" : undefined }}><path d="M6 9l6 6 6-6" /></svg>
                        </button>
                        <span className="farbpunkt" />
                        <a href={p.url} className="gt-name">{p.name}</a>
                        {p.archiviert && <span className="badge">{t("archiviert")}</span>}
                        <span className={`gt-daten mono${ueberzug ? " gt-daten--ueberzug" : ""}`} title={ueberzug || undefined}>
                          {zr.von ? kurzDatum(zr.von) : ""}{zr.bis ? `–${kurzDatum(zr.bis)}` : ""}
                        </span>
                        {optionen?.darf_verwalten && (
                          <button type="button" className="knopf knopf--text gt-entfernen" aria-label={t("projekt_entfernen", { name: p.name })}
                            title={t("projekt_entfernen", { name: p.name })} onClick={() => projektZuordnen(p, false)}>×</button>
                        )}
                      </div>
                      <div className="gt-zeit">
                        {beginn && ende && (
                          <Balken klasse="gt-balken gt-balken--projekt" {...balken(beginn, ende, start, px)} bearbeitbar={bearbeiten}
                            titel={`${p.name}: ${langDatum(beginn)} – ${langDatum(ende)}`}
                            onZiehen={(ev, art) => ziehen(ev, art, { art: "projekt", id: p.id, beginn, ende },
                              (b, en) => projektTermine(p, b, en), () => bearbeiten && setDialog({ art: "projekt", projekt: p }))}
                            onOeffnen={() => bearbeiten && setDialog({ art: "projekt", projekt: p })} />
                        )}
                        {!(beginn && ende) && zr.von && zr.bis && (
                          <div className="gt-balken gt-balken--projekt gt-balken--abgeleitet" style={stil(balken(zr.von, zr.bis, start, px))}
                            title={`${p.name}: ${langDatum(zr.von)} – ${langDatum(zr.bis)}`} />
                        )}
                        {[zr.vorne, zr.hinten].map((teil) => teil && (
                          <div key={teil.von} className="gt-ueberzug" style={stil(balken(teil.von, teil.bis, start, px))} title={ueberzug} />
                        ))}
                        {p.ist_von && p.ist_bis && <div className="gt-ist" style={{ ...stil(balken(p.ist_von, p.ist_bis, start, px)) }} />}
                      </div>
                    </div>
                  );
                }
                const a = z.aufgabe;
                const v = vorschau?.art === "aufgabe" && vorschau.id === a.id ? vorschau : null;
                const mit = vorschau?.art === "aufgabe" && vorschau.tage && a.eltern === vorschau.id ? vorschau.tage : 0;
                const beginn = v ? v.beginn : verschieben(a.beginn, mit);
                const ende = v ? v.ende : verschieben(a.ende, mit);
                const projektFarbe = daten.projekte.find((p) => p.id === a.projekt_id)?.farbe ?? daten.externe_projekte[a.projekt_id]?.farbe ?? "grau";
                const editierbar = bearbeiten && !a.extern;
                const oeffnen = () => (editierbar ? setDialog({ art: "aufgabe", aufgabe: a }) : (window.location.href = a.url));
                const titel = `${a.titel}${beginn ? ` · ${langDatum(beginn)}` : ""}${ende ? ` – ${langDatum(ende)}` : ""}`;
                return (
                  <div key={`a${a.id}`} className={`gt-zeile pf-${projektFarbe}${a.erledigt ? " gt-zeile--erledigt" : ""}`}>
                    <div className={`gt-links gt-links--aufgabe${a.eltern && !a.extern ? " gt-links--unter" : ""}${a.kinder.length ? " gt-links--haupt" : ""}`}>
                      {a.kinder.length > 0 && (
                        <button type="button" className="gt-klapp" aria-expanded={!z.zu}
                          aria-label={t(z.zu ? "unter_ausklappen" : "unter_einklappen", { name: a.titel })}
                          title={t(z.zu ? "unter_ausklappen" : "unter_einklappen", { name: a.titel })}
                          onClick={() => unterUmschalten(a.id)}>
                          <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.6" aria-hidden="true" style={{ transform: z.zu ? "rotate(-90deg)" : undefined }}><path d="M6 9l6 6 6-6" /></svg>
                        </button>
                      )}
                      <a href={a.url} className="gt-name" title={a.titel}>{a.erledigt ? "✓ " : ""}{a.titel}</a>
                      {z.zu && <span className="gedaempft klein gt-anzahl">{a.kinder.length}</span>}
                      {a.extern && <span className="gedaempft klein">{daten.externe_projekte[a.projekt_id]?.name}</span>}
                      {!beginn && !ende && <span className="gedaempft klein gt-ohne-termin">{t("ohne_termin")}</span>}
                      {editierbar && (
                        <button type="button" className="knopf knopf--text gt-termine" aria-label={t("termine")} title={t("termine")}
                          onClick={() => setDialog({ art: "aufgabe", aufgabe: a })}>
                          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true">
                            <rect x="3" y="5" width="18" height="16" rx="2" /><path d="M3 10h18M8 3v4M16 3v4" />
                          </svg>
                        </button>
                      )}
                    </div>
                    <div className="gt-zeit" onPointerDown={(ev) => aufziehen(ev, a)}>
                      {beginn && ende && (
                        <Balken klasse={`gt-balken${a.sammel ? " gt-balken--sammel" : ""}`} {...balken(beginn, ende, start, px)}
                          bearbeitbar={editierbar} griffe={!a.sammel} aufgabe={a.id} titel={titel}
                          onZiehen={(ev, art) => ziehen(ev, art, { art: "aufgabe", id: a.id, beginn, ende }, (b, en) => aufgabeTermine(a, b, en), oeffnen)}
                          onOeffnen={oeffnen}
                          onVerbinden={editierbar ? (ev) => verbindenStart(ev, a, i, x(ende, start, px) + px) : undefined} />
                      )}
                      {!beginn && ende && (
                        <div className={`gt-meilenstein${editierbar ? " gt-meilenstein--bearbeitbar" : ""}`} data-aufgabe={a.id} title={titel}
                          style={{ left: x(ende, start, px) + px / 2 - 8 }}
                          onPointerDown={(ev) => editierbar ? ziehen(ev, "mitte", { art: "aufgabe", id: a.id, beginn, ende }, (b, en) => aufgabeTermine(a, b, en), oeffnen) : undefined}
                          onClick={editierbar ? undefined : oeffnen} />
                      )}
                      {beginn && !ende && (
                        <Balken klasse="gt-balken gt-balken--offen" {...balken(beginn, beginn, start, px)} bearbeitbar={editierbar} aufgabe={a.id} titel={titel}
                          onZiehen={(ev, art) => ziehen(ev, art === "rechts" ? "mitte" : art, { art: "aufgabe", id: a.id, beginn, ende }, (b, en) => aufgabeTermine(a, b, en), oeffnen)}
                          onOeffnen={oeffnen} />
                      )}
                      {a.ist_von && a.ist_bis && <div className="gt-ist" style={stil(balken(a.ist_von, a.ist_bis, start, px))} />}
                    </div>
                  </div>
                );
              })}

              <svg className="gt-pfeile" style={{ left: LINKS }} width={breite} height={liste.length * ZEILE} aria-hidden="true">
                <defs>
                  <marker id="gt-spitze" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
                    <path d="M0,0 L10,5 L0,10 z" fill="#7d847f" />
                  </marker>
                  <marker id="gt-spitze-rot" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
                    <path d="M0,0 L10,5 L0,10 z" fill="#c2410c" />
                  </marker>
                </defs>
                {pfeilListe.map((p) => {
                  const erste = p.abhaengigkeiten[0];
                  const name = t(p.verletzt ? "abh_verletzt" : "abh", {
                    a: daten.aufgaben[erste.vorher]?.titel ?? "", b: daten.aufgaben[erste.nachher]?.titel ?? "",
                  });
                  return (
                    <g key={p.schluessel} className={`gt-pfeil${p.verletzt ? " gt-pfeil--verletzt" : ""}`}
                      onClick={bearbeiten && p.abhaengigkeiten.length === 1 ? () => abhaengigkeitLoeschen(erste.id) : undefined}>
                      <title>{name}</title>
                      <path d={pfad(p)} className="gt-pfeil__treffer" />
                      <path d={pfad(p)} className="gt-pfeil__linie" markerEnd={`url(#${p.verletzt ? "gt-spitze-rot" : "gt-spitze"})`} />
                    </g>
                  );
                })}
                {verbinden && <line x1={verbinden.x1} y1={verbinden.y1} x2={verbinden.x2} y2={verbinden.y2} className="gt-verbinden" />}
              </svg>
            </div>
          </div>
        </div>
      )}

      <div className="legende">
        <span><i className="gt-legende-geplant" />{t("legende_geplant")}</span>
        <span><i className="gt-legende-ist" />{t("legende_ist")}</span>
        <span><i className="gt-legende-sammel" />{t("legende_sammel")}</span>
        <span><i className="gt-legende-meilenstein" />{t("legende_meilenstein")}</span>
        <span><i className="gt-legende-ueberzug" />{t("legende_ueberzug")}</span>
        <span><i className="gt-legende-verletzt" />{t("legende_verletzt")}</span>
        <span><i style={{ background: "var(--feiertag)" }} />{t("legende_frei")}</span>
      </div>

      {dialog && daten && (
        <TermineDialog
          dialog={dialog}
          daten={daten}
          onSchliessen={() => setDialog(null)}
          onSpeichern={(beginn, ende) => {
            setDialog(null);
            if (dialog.art === "aufgabe") aufgabeTermine(dialog.aufgabe, beginn, ende);
            else projektTermine(dialog.projekt, beginn, ende);
          }}
          bearbeiten={bearbeiten}
          onVorgaenger={(vorher) => { if (dialog.art === "aufgabe") abhaengigkeitAnlegen(vorher, dialog.aufgabe.id); }}
          onVorgaengerLoeschen={(id) => abhaengigkeitLoeschen(id)}
        />
      )}
      {bestaetigung.dialog}
    </div>
  );
}

function stil(b: { links: number; breite: number }): React.CSSProperties {
  return { left: b.links, width: b.breite };
}

interface BalkenProps {
  klasse: string;
  links: number;
  breite: number;
  titel: string;
  bearbeitbar: boolean;
  /** Ränder ziehen ändert die Dauer – nicht bei Sammelaufgaben */
  griffe?: boolean;
  aufgabe?: number;
  onZiehen: (ev: React.PointerEvent, art: "mitte" | "links" | "rechts") => void;
  onOeffnen: () => void;
  onVerbinden?: (ev: React.PointerEvent) => void;
}

function Balken({ klasse, links, breite, titel, bearbeitbar, griffe = true, aufgabe, onZiehen, onOeffnen, onVerbinden }: BalkenProps) {
  return (
    <div className={`${klasse}${bearbeitbar ? " gt-balken--bearbeitbar" : ""}`} style={{ left: links, width: Math.max(breite, 6) }}
      title={titel} data-aufgabe={aufgabe} role={bearbeitbar ? "button" : "link"} tabIndex={0} aria-label={titel}
      onPointerDown={(ev) => onZiehen(ev, "mitte")}
      onKeyDown={(ev) => { if (ev.key === "Enter" || ev.key === " ") { ev.preventDefault(); onOeffnen(); } }}>
      {bearbeitbar && griffe && <span className="gt-griff gt-griff--links" onPointerDown={(ev) => onZiehen(ev, "links")} />}
      {bearbeitbar && griffe && <span className="gt-griff gt-griff--rechts" onPointerDown={(ev) => onZiehen(ev, "rechts")} />}
      {onVerbinden && <span className="gt-verbinder" onPointerDown={onVerbinden} title="A → B" />}
    </div>
  );
}

function TermineDialog({ dialog, daten, bearbeiten, onSchliessen, onSpeichern, onVorgaenger, onVorgaengerLoeschen }: {
  dialog: Dialog;
  daten: GDaten;
  bearbeiten: boolean;
  onSchliessen: () => void;
  onSpeichern: (beginn: string | null, ende: string | null) => void;
  onVorgaenger: (vorher: number) => void;
  onVorgaengerLoeschen: (id: number) => void;
}) {
  const obj = dialog.art === "aufgabe" ? dialog.aufgabe : dialog.projekt;
  const [beginn, setBeginn] = useState(obj.beginn ?? "");
  const [ende, setEnde] = useState(obj.ende ?? "");
  const titel = dialog.art === "aufgabe" ? dialog.aufgabe.titel : dialog.projekt.name;
  // Sammelaufgabe: nur der Beginn lässt sich ändern, das verschiebt alle Unteraufgaben (Dauer bleibt)
  const sammel = dialog.art === "aufgabe" && dialog.aufgabe.sammel;
  const neuerBeginn = (wert: string) => {
    if (sammel && wert && obj.beginn && obj.ende) setEnde(plusTage(obj.ende, tageZwischen(obj.beginn, wert)));
    setBeginn(wert);
  };
  return (
    <Modal titel={t(dialog.art === "aufgabe" ? "termine_titel" : "projekt_termine_titel", { titel })} onSchliessen={onSchliessen}>
      <form className="formular" onSubmit={(ev) => { ev.preventDefault(); onSpeichern(beginn || null, ende || null); }}>
        <div className="formular__zeile">
          <label className="feld">{t("beginn")}<input type="date" value={beginn} max={sammel ? undefined : ende || undefined} required={sammel} onChange={(ev) => neuerBeginn(ev.target.value)} /></label>
          <label className="feld">{t("ende")}<input type="date" value={ende} min={beginn || undefined} disabled={sammel} onChange={(ev) => setEnde(ev.target.value)} /></label>
        </div>
        <div className="formular__aktionen">
          <button type="submit" className="knopf knopf--primaer">{t("speichern")}</button>
          <button type="button" className="knopf" onClick={onSchliessen}>{t("abbrechen")}</button>
          <span className="luecke" />
          {!sammel && <button type="button" className="knopf" onClick={() => onSpeichern(null, null)}>{t("termine_loeschen")}</button>}
        </div>
      </form>
      {dialog.art === "aufgabe" && (
        <VorgaengerWahl aufgabe={daten.aufgaben[dialog.aufgabe.id] ?? dialog.aufgabe} daten={daten} bearbeiten={bearbeiten}
          onHinzufuegen={onVorgaenger} onEntfernen={onVorgaengerLoeschen} />
      )}
    </Modal>
  );
}
