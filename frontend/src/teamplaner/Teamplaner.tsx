import {
  DndContext,
  DragOverlay,
  PointerSensor,
  pointerWithin,
  useSensor,
  useSensors,
  type DragEndEvent,
  type DragOverEvent,
  type DragStartEvent,
} from "@dnd-kit/core";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { toast } from "../lib/toast";
import { api, ApiFehler, CLIENT_ID } from "./api";
import { BearbeitenDialog, useBestaetigung } from "./Dialoge";
import { useEntprellt, useGespeichert, useMediaQuery } from "./hooks";
import {
  doppelbelegungen,
  kalenderwoche,
  kurzDatum,
  kurzTag,
  langDatum,
  montagVon,
  plusTage,
  position,
  verschieben,
  type Position,
} from "./logik";
import { Palette } from "./Palette";
import { RasterAnsicht, type Vorschau } from "./Raster";
import { Tagesansicht } from "./Tagesansicht";
import { t } from "./texte";
import type { Aufgabe, FreigabeTag, Eintrag, Optionen, PaletteDaten, Person, Projekt, Raster } from "./typen";

interface Einstellungen {
  ansicht: string;
  wochen: number;
  bereich: number | null;
  gewerk: number | null;
  tag: number | null;
  projekt: number | null;
  archivierte: boolean;
  paletteModus: "offen" | "projekt";
  paletteProjekt: number | null;
}

type Ziehdaten =
  | { typ: "neu-einteilung"; aufgabe: Aufgabe; projekt?: Projekt }
  | { typ: "neu-abwesenheit" }
  | { typ: "einteilung" | "abwesenheit"; eintrag: Eintrag; position: Position; griff: { current: number } };

type DialogZustand =
  | { art: "bearbeiten"; eintrag: Eintrag }
  | { art: "neu-einteilung"; aufgabe: Aufgabe; projekt?: Projekt }
  | { art: "neu-abwesenheit" };

function heuteLokal() {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

export function Teamplaner({ planen }: { planen: boolean }) {
  const heute = heuteLokal();
  const [e, setE] = useGespeichert<Einstellungen>("teamplaner-einstellungen", {
    ansicht: "", wochen: 2, bereich: null, gewerk: null, tag: null, projekt: null, archivierte: false,
    paletteModus: "offen", paletteProjekt: null,
  });
  const [start, setStart] = useState(() => montagVon(heute));
  const [optionen, setOptionen] = useState<Optionen | null>(null);
  const [raster, setRaster] = useState<Raster | null>(null);
  const [ladefehler, setLadefehler] = useState<string | null>(null);
  const [palette, setPalette] = useState<PaletteDaten | null>(null);
  const [suche, setSuche] = useState("");
  const [vorschau, setVorschau] = useState<Vorschau | null>(null);
  const [ziehen, setZiehen] = useState<{ daten: Ziehdaten; griffSpalte: number } | null>(null);
  const [dialog, setDialog] = useState<DialogZustand | null>(null);
  const [filterOffen, setFilterOffen] = useState(false);
  const bestaetigung = useBestaetigung();
  const mobil = useMediaQuery("(max-width: 760px)");
  const darfPlanen = planen && !mobil;

  // Am Handy immer 4 Wochen – man blättert dort ohnehin Tag für Tag
  const wochen = mobil ? 4 : [1, 2, 4].includes(e.wochen) ? e.wochen : 2;
  const bis = plusTage(start, 7 * wochen - 1);
  const ansicht = optionen?.ansichten.find((a) => a.id === e.ansicht) ?? optionen?.ansichten[0];

  // Rückmeldungen als Toast über dem Raster, damit nichts springt
  const zeige = useCallback((text: string, art: "info" | "fehler" = "fehler", rueckgaengig?: () => void) => {
    toast(text, { art, aktion: rueckgaengig && { text: t("rueckgaengig"), ausfuehren: rueckgaengig } });
  }, []);

  // ---------- Laden ----------
  useEffect(() => {
    api.optionen().then(setOptionen).catch((f) => setLadefehler(f.message));
  }, []);

  const rasterNr = useRef(0);
  const ladeRaster = useCallback(async (hintergrund = false) => {
    if (!ansicht) return;
    const nr = ++rasterNr.current;
    try {
      const daten = await api.raster(ansicht.id, start, bis, e.archivierte, hintergrund);
      if (nr === rasterNr.current) {
        setRaster(daten);
        setLadefehler(null);
      }
    } catch (f) {
      if (nr === rasterNr.current) setLadefehler(f instanceof Error ? f.message : t("laden_fehlgeschlagen"));
    }
  }, [ansicht, start, bis, e.archivierte]);
  useEffect(() => {
    ladeRaster();
  }, [ladeRaster]);

  const paletteNr = useRef(0);
  const ladePalette = useCallback(async (hintergrund = false) => {
    if (!darfPlanen) return;
    if (e.paletteModus === "projekt" && !e.paletteProjekt) {
      setPalette({ aufgaben: [], projekte: {} });
      return;
    }
    const nr = ++paletteNr.current;
    try {
      const daten = await api.palette({
        modus: e.paletteModus,
        projekt: e.paletteModus === "projekt" ? e.paletteProjekt : e.projekt,
        gewerk: e.gewerk,
        tag: e.tag,
        q: suche,
      }, hintergrund);
      if (nr === paletteNr.current) setPalette(daten);
    } catch {
      /* Palette ist nicht kritisch */
    }
  }, [darfPlanen, e.paletteModus, e.paletteProjekt, e.projekt, e.gewerk, e.tag, suche]);
  useEffect(() => {
    const t = window.setTimeout(() => ladePalette(), 200);
    return () => window.clearTimeout(t);
  }, [ladePalette]);

  // ---------- Live-Aktualisierung ----------
  const neuLaden = useEntprellt(() => {
    ladeRaster(true);
    ladePalette(true);
  }, 300);
  useEffect(() => {
    let quelle: EventSource | null = null;
    let timer = 0;
    let wartezeit = 2000;
    let getrennt = false;
    const verbinden = () => {
      quelle = new EventSource("/api/planung/stream");
      quelle.addEventListener("open", () => {
        // Nach einer Unterbrechung (Neustart, Update) verpasste Änderungen nachladen
        if (getrennt) neuLaden();
        getrennt = false;
        wartezeit = 2000;
      });
      quelle.addEventListener("planung", (ev) => {
        const daten = JSON.parse((ev as MessageEvent).data);
        if (daten.client !== CLIENT_ID) neuLaden();
      });
      quelle.addEventListener("error", () => {
        getrennt = true;
        // Bei einer HTTP-Fehlerantwort (z. B. Wartungsseite während eines Updates) gibt der
        // Browser endgültig auf – dann selbst mit wachsendem Abstand neu verbinden
        if (quelle?.readyState === EventSource.CLOSED) {
          quelle.close();
          timer = window.setTimeout(verbinden, wartezeit);
          wartezeit = Math.min(wartezeit * 2, 30000);
        }
      });
    };
    verbinden();
    return () => {
      window.clearTimeout(timer);
      quelle?.close();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // ---------- Abgeleitete Daten ----------
  const spalten = useMemo(() => raster?.tage.map((t) => t.datum) ?? [], [raster]);
  const frei = useMemo(
    () => new Map((raster?.tage ?? []).filter((t) => t.frei).map((t) => [t.datum, t.frei as string])),
    [raster],
  );
  const infos = useMemo(
    () => new Map((raster?.tage ?? []).filter((t) => t.info).map((t) => [t.datum, t.info])),
    [raster],
  );
  // Tagesfreigabe je Tag (alle Tage, auch ohne Freigabe); null = Zeile ausgeblendet (Admin-Einstellung)
  const tagesfreigaben = useMemo(() => {
    if (!raster?.freigabe_zeile) return null;
    const namen = new Map(raster.freigabe_stufen.map((s) => [s.wert, s.name]));
    return new Map<string, FreigabeTag>(raster.tage.map((t) => [
      t.datum, { stufe: t.freigabe, name: t.freigabe ? namen.get(t.freigabe) ?? t.freigabe : "", von: t.freigabe ? t.freigabe_von : "" },
    ]));
  }, [raster]);
  const personen = useMemo(
    () =>
      (raster?.personen ?? []).filter(
        (p) => (!e.bereich || p.bereich_id === e.bereich) && (!e.gewerk || p.gewerk_ids.includes(e.gewerk)),
      ),
    [raster, e.bereich, e.gewerk],
  );
  const gruppen = useMemo(
    () =>
      (raster?.bereiche ?? [])
        .map((b) => ({
          id: b.id,
          name: b.name,
          personen: personen.filter((p) => p.bereich_id === b.id).sort((a, c) => Number(c.ich) - Number(a.ich)),
        }))
        .filter((g) => g.personen.length > 0),
    [raster, personen],
  );
  const eintraegeJePerson = useMemo(() => {
    const karte = new Map<number, Eintrag[]>();
    const hinzu = (pid: number, eintrag: Eintrag) => {
      const liste = karte.get(pid) ?? [];
      liste.push(eintrag);
      karte.set(pid, liste);
    };
    raster?.einteilungen.forEach((x) => hinzu(x.person_id, { art: "einteilung", ...x }));
    raster?.abwesenheiten.forEach((x) => hinzu(x.person_id, { art: "abwesenheit", ...x }));
    return karte;
  }, [raster]);
  const konflikte = useMemo(
    () => doppelbelegungen(raster?.einteilungen ?? [], raster?.abwesenheiten ?? [], frei),
    [raster, frei],
  );
  const gedimmt = useCallback(
    (eintrag: Eintrag) => {
      if (eintrag.art !== "einteilung" || !raster) return false;
      const a = raster.aufgaben[eintrag.aufgabe_id];
      if (!a) return false;
      if (e.projekt && a.projekt_id !== e.projekt) return true;
      if (e.tag && !raster.projekte[a.projekt_id]?.tags.includes(e.tag)) return true;
      return false;
    },
    [raster, e.projekt, e.tag],
  );
  // Systemkonten (auswaehlbar = false) behalten ihre Balken, bekommen aber keine neuen
  const einteilbar = useMemo(() => (raster?.personen ?? []).filter((p) => p.einteilbar && p.auswaehlbar), [raster]);

  // ---------- Speichern ----------
  const lokal = (fn: (r: Raster) => Raster) => setRaster((r) => (r ? fn(r) : r));

  const mitFeiertag = async <T,>(aufruf: (bestaetigt: boolean) => Promise<T>, von: string, bis_: string, pruefen: boolean) => {
    let bestaetigt = false;
    if (pruefen && von === bis_ && frei.has(von)) {
      const ok = await bestaetigung.fragen(
        t("feiertag_frage", { datum: `${kurzTag(von)} ${langDatum(von)}`, name: frei.get(von) ?? "" }),
      );
      if (!ok) return null;
      bestaetigt = true;
    }
    try {
      return await aufruf(bestaetigt);
    } catch (f) {
      if (f instanceof ApiFehler && f.code === "feiertag_bestaetigung" && !bestaetigt) {
        if (await bestaetigung.fragen(f.message)) return aufruf(true);
        return null;
      }
      throw f;
    }
  };

  const speichern = async (aktion: () => Promise<unknown>) => {
    try {
      await aktion();
    } catch (f) {
      zeige(f instanceof ApiFehler ? f.message : t("speichern_fehlgeschlagen"));
    } finally {
      ladeRaster();
      ladePalette();
    }
  };

  const einteilen = (aufgabe: Aufgabe, projekt: Projekt | undefined, personId: number, von: string, bis_: string, bestaetigt = false) =>
    speichern(async () => {
      lokal((r) => ({
        ...r,
        einteilungen: [...r.einteilungen, { id: -Date.now(), aufgabe_id: aufgabe.id, person_id: personId, von, bis: bis_, version: 0 }],
        aufgaben: { ...r.aufgaben, [aufgabe.id]: r.aufgaben[aufgabe.id] ?? aufgabe },
        projekte: projekt ? { ...r.projekte, [projekt.id]: r.projekte[projekt.id] ?? projekt } : r.projekte,
      }));
      await mitFeiertag(
        (b) => api.einteilungAnlegen({ aufgabe_id: aufgabe.id, person_id: personId, von, bis: bis_, feiertag_bestaetigt: b || bestaetigt }),
        von, bis_, !bestaetigt,
      );
    });

  const abwesenheitAnlegen = (personId: number, von: string, bis_: string) =>
    speichern(async () => {
      lokal((r) => ({ ...r, abwesenheiten: [...r.abwesenheiten, { id: -Date.now(), person_id: personId, von, bis: bis_, version: 0 }] }));
      await api.abwesenheitAnlegen({ person_id: personId, von, bis: bis_ });
    });

  const aendern = (eintrag: Eintrag, werte: { person_id?: number; von?: string; bis?: string }) =>
    speichern(async () => {
      lokal((r) =>
        eintrag.art === "einteilung"
          ? { ...r, einteilungen: r.einteilungen.map((x) => (x.id === eintrag.id ? { ...x, ...werte } : x)) }
          : { ...r, abwesenheiten: r.abwesenheiten.map((x) => (x.id === eintrag.id ? { ...x, ...werte } : x)) },
      );
      if (eintrag.art === "einteilung") {
        const von = werte.von ?? eintrag.von;
        const bis_ = werte.bis ?? eintrag.bis;
        const datumGeaendert = von !== eintrag.von || bis_ !== eintrag.bis;
        await mitFeiertag((b) => api.einteilungAendern(eintrag.id, { version: eintrag.version, ...werte, feiertag_bestaetigt: b }), von, bis_, datumGeaendert);
      } else {
        await api.abwesenheitAendern(eintrag.id, { version: eintrag.version, ...werte });
      }
    });

  const loeschen = useCallback(
    (eintrag: Eintrag) =>
      speichern(async () => {
        lokal((r) =>
          eintrag.art === "einteilung"
            ? { ...r, einteilungen: r.einteilungen.filter((x) => x.id !== eintrag.id) }
            : { ...r, abwesenheiten: r.abwesenheiten.filter((x) => x.id !== eintrag.id) },
        );
        if (eintrag.art === "einteilung") {
          const aufgabe = raster?.aufgaben[eintrag.aufgabe_id];
          const projekt = aufgabe ? raster?.projekte[aufgabe.projekt_id] : undefined;
          await api.einteilungLoeschen(eintrag.id, eintrag.version);
          if (aufgabe) {
            zeige(t("entfernt", { titel: aufgabe.titel }), "info", () => einteilen(aufgabe, projekt, eintrag.person_id, eintrag.von, eintrag.bis, true));
          }
        } else {
          await api.abwesenheitLoeschen(eintrag.id, eintrag.version);
          zeige(t("abwesenheit_entfernt"), "info", () => abwesenheitAnlegen(eintrag.person_id, eintrag.von, eintrag.bis));
        }
      }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [raster],
  );

  const groesse = useCallback(
    (eintrag: Eintrag, von: string, bis_: string) => aendern(eintrag, { von, bis: bis_ }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [raster, frei],
  );
  const oeffnen = useCallback((eintrag: Eintrag) => setDialog({ art: "bearbeiten", eintrag }), []);

  const infoSetzen = (datum: string, text: string) =>
    speichern(async () => {
      lokal((r) => ({ ...r, tage: r.tage.map((x) => (x.datum === datum ? { ...x, info: text } : x)) }));
      await api.tagesinfo(datum, text);
    });

  const freigabeSetzen = (datum: string, stufe: string) =>
    speichern(async () => {
      // Der Name kommt mit dem Neuladen danach; bei „keine Freigabe“ gibt es keinen
      lokal((r) => ({ ...r, tage: r.tage.map((x) => (x.datum === datum ? { ...x, freigabe: stufe, freigabe_von: stufe ? x.freigabe_von : "" } : x)) }));
      await api.tagesfreigabe(datum, stufe);
    });

  // ---------- Drag-and-drop ----------
  const sensoren = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 5 } }));

  const zielBereich = (daten: Ziehdaten, griffSpalte: number, spalte: number) => {
    if (daten.typ === "neu-einteilung" || daten.typ === "neu-abwesenheit") {
      return { von: spalten[spalte], bis: spalten[spalte] };
    }
    return verschieben(daten.eintrag.von, daten.eintrag.bis, spalte - griffSpalte);
  };

  const beimStart = (ev: DragStartEvent) => {
    const daten = ev.active.data.current as Ziehdaten;
    let griffSpalte = 0;
    if (daten.typ === "einteilung" || daten.typ === "abwesenheit") {
      griffSpalte = daten.position.start + daten.griff.current;
    }
    setZiehen({ daten, griffSpalte });
  };

  const beimUeber = (ev: DragOverEvent) => {
    if (!ev.over || !ziehen) {
      setVorschau(null);
      return;
    }
    const { personId, spalte } = ev.over.data.current as { personId: number; spalte: number };
    const { von, bis: b } = zielBereich(ziehen.daten, ziehen.griffSpalte, spalte);
    const pos = position(von, b, spalten);
    const art = ziehen.daten.typ === "abwesenheit" || ziehen.daten.typ === "neu-abwesenheit" ? "abwesenheit" : "einteilung";
    setVorschau(pos ? { personId, start: pos.start, ende: pos.ende, art } : null);
  };

  const beimEnde = (ev: DragEndEvent) => {
    const z = ziehen;
    setVorschau(null);
    setZiehen(null);
    if (!ev.over || !z) return;
    const { personId, spalte } = ev.over.data.current as { personId: number; spalte: number };
    const { von, bis: b } = zielBereich(z.daten, z.griffSpalte, spalte);
    if (z.daten.typ === "neu-einteilung") {
      einteilen(z.daten.aufgabe, z.daten.projekt, personId, von, b);
    } else if (z.daten.typ === "neu-abwesenheit") {
      abwesenheitAnlegen(personId, von, b);
    } else {
      const eintrag = z.daten.eintrag;
      const werte: { person_id?: number; von?: string; bis?: string } = {};
      if (personId !== eintrag.person_id) werte.person_id = personId;
      if (von !== eintrag.von || b !== eintrag.bis) Object.assign(werte, { von, bis: b });
      if (Object.keys(werte).length) aendern(eintrag, werte);
    }
  };

  // ---------- Darstellung ----------
  const ansichtWaehlen = (id: string) => {
    const a = optionen?.ansichten.find((x) => x.id === id);
    const f = (a?.filter ?? {}) as Record<string, number | null | undefined>;
    setE({
      ansicht: id,
      wochen: f.wochen ?? e.wochen,
      gewerk: f.gewerk ?? null,
      projekt: f.projekt ?? null,
      tag: f.tag ?? null,
      bereich: null,
    });
  };

  const aktiveFilter = [e.bereich, e.gewerk, e.tag, e.projekt].filter(Boolean).length + (e.archivierte ? 1 : 0);
  const kwText = wochen > 1 ? `${kalenderwoche(start)}–${kalenderwoche(bis)}` : String(kalenderwoche(start));
  const zeitraum = mobil ? t("kw", { n: kwText }) : `${t("kw", { n: kwText })} · ${kurzDatum(start)}–${langDatum(bis)}`;
  const ziehTitel = (() => {
    const d = ziehen?.daten;
    if (!d) return "";
    if (d.typ === "neu-einteilung") return d.aufgabe.titel;
    if (d.typ === "neu-abwesenheit" || d.eintrag.art === "abwesenheit") return t("abwesend");
    return raster?.aufgaben[d.eintrag.aufgabe_id]?.titel ?? "";
  })();

  const bearbeitenEintrag = dialog?.art === "bearbeiten" ? dialog.eintrag : null;
  const dialogAufgabe =
    dialog?.art === "neu-einteilung" ? dialog.aufgabe
      : bearbeitenEintrag?.art === "einteilung" ? raster?.aufgaben[bearbeitenEintrag.aufgabe_id] : undefined;

  // Ansicht: am Desktop ganz rechts in der Werkzeugzeile, am Handy neben der Überschrift
  const ansichtWahl = optionen && (
    <label className="feld tp-ansichtwahl">
      <span className="sr-only">{t("ansicht")}</span>
      <select value={ansicht?.id ?? ""} onChange={(ev) => ansichtWaehlen(ev.target.value)}>
        {optionen.ansichten.map((a) => (
          <option key={a.id} value={a.id}>{a.name}{planen && a.recht === "sehen" && a.id !== "ich" ? t("nur_sehen") : ""}</option>
        ))}
      </select>
    </label>
  );

  return (
    <div className="tp">
      <div className="seitenkopf">
        <div className="seitenkopf__titel">
          <h1>{darfPlanen ? t("titel_planen") : t("titel_lesen")}</h1>
          {ansicht && <div className="nur-drucken">{ansicht.name} · {kurzDatum(start)}–{langDatum(bis)}</div>}
        </div>
        {mobil && ansichtWahl}
      </div>

      <div className="tp-werkzeuge nicht-drucken">
        <button type="button" className={`knopf tp-filter-knopf${aktiveFilter ? " tp-filter-knopf--aktiv" : ""}`}
          aria-expanded={filterOffen} aria-controls="tp-filter-optionen" aria-label={t("filter")} title={t("filter")}
          onClick={() => setFilterOffen(!filterOffen)}>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true"><path d="M3 5h18l-7 9v5l-4 2v-7z" /></svg>
          <span className="tp-filter-text">{t("filter")}</span>{aktiveFilter ? <span className="tp-filter-anzahl">{aktiveFilter}</span> : null}
        </button>
        <button type="button" className="knopf tp-drucken" onClick={() => window.print()}>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinejoin="round" aria-hidden="true"><path d="M6 9V3h12v6M6 18H4a1 1 0 0 1-1-1v-6a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2v6a1 1 0 0 1-1 1h-2" /><path d="M6 14h12v7H6z" /></svg>
          {t("drucken")}
        </button>
        <div id="tp-filter-optionen" className={`tp-filter-optionen${filterOffen ? " offen" : ""}`}>
        {optionen && (
          <>
            <label className="feld">
              {t("bereich")}
              <select value={e.bereich ?? ""} onChange={(ev) => setE({ bereich: ev.target.value ? Number(ev.target.value) : null })}>
                <option value="">{t("alle_bereiche")}</option>
                {optionen.bereiche.map((b) => <option key={b.id} value={b.id}>{b.name}</option>)}
              </select>
            </label>
            <label className="feld">
              {t("gewerk")}
              <select value={e.gewerk ?? ""} onChange={(ev) => setE({ gewerk: ev.target.value ? Number(ev.target.value) : null })}>
                <option value="">{t("alle_gewerke")}</option>
                {optionen.gewerke.map((g) => <option key={g.id} value={g.id}>{g.name}</option>)}
              </select>
            </label>
            <label className="feld">
              {t("projekt_tag")}
              <select value={e.tag ?? ""} onChange={(ev) => setE({ tag: ev.target.value ? Number(ev.target.value) : null })}>
                <option value="">{t("alle_tags")}</option>
                {optionen.tags.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
              </select>
            </label>
            <label className="feld">
              {t("projekt")}
              <select value={e.projekt ?? ""} onChange={(ev) => setE({ projekt: ev.target.value ? Number(ev.target.value) : null })}>
                <option value="">{t("alle_projekte")}</option>
                {optionen.projekte.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
              </select>
            </label>
          </>
        )}
        <label className="feld feld--zeile">
          <input type="checkbox" checked={e.archivierte} onChange={(ev) => setE({ archivierte: ev.target.checked })} />
          {t("archivierte_anzeigen")}
        </label>
        </div>
        <span className="luecke" />
        <div className="tp-werkzeuge__rechts">
        <div className="zeile">
          <button type="button" className="knopf knopf--icon" aria-label={t("zeitraum_vorher")} onClick={() => setStart(plusTage(start, -7 * wochen))}>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true"><path d="M15 18l-6-6 6-6" /></svg>
          </button>
          <button type="button" className="knopf" onClick={() => setStart(montagVon(heute))}>{t("heute")}</button>
          <button type="button" className="knopf knopf--icon" aria-label={t("zeitraum_nachher")} onClick={() => setStart(plusTage(start, 7 * wochen))}>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true"><path d="M9 18l6-6-6-6" /></svg>
          </button>
          <span className="mono tp-zeitraum" aria-live="polite">{zeitraum}</span>
        </div>
        {!mobil && (
          <div className="knopfgruppe" role="group" aria-label={t("zeitraum")}>
            {[1, 2, 4].map((w) => (
              <button key={w} type="button" aria-pressed={wochen === w} onClick={() => setE({ wochen: w })}>
                {t(w === 1 ? "woche" : "wochen", { n: w })}
              </button>
            ))}
          </div>
        )}
        {!mobil && ansichtWahl}
        </div>
      </div>

      {ladefehler && <div className="meldung meldung--error" role="alert">{ladefehler}</div>}
      {planen && mobil && <div className="meldung">{t("nur_desktop")}</div>}

      {!raster ? (
        <div className="karte leer">{t("laedt")}</div>
      ) : mobil ? (
        <Tagesansicht spalten={spalten} frei={frei} infos={infos} tagesfreigaben={tagesfreigaben} freigabeName={raster?.freigabe_name ?? ""} heute={heute} gruppen={gruppen} eintraegeJePerson={eintraegeJePerson}
          aufgaben={raster.aufgaben} projekte={raster.projekte} />
      ) : (
        <DndContext sensors={sensoren} collisionDetection={pointerWithin} onDragStart={beimStart} onDragOver={beimUeber}
          onDragEnd={beimEnde} onDragCancel={() => { setVorschau(null); setZiehen(null); }}>
          <div className="tp-haupt">
            <section className="tp-rahmen karte">
              {gruppen.length === 0 ? (
                <div className="leer">{t("keine_personen")}</div>
              ) : (
                <RasterAnsicht
                  spalten={spalten} frei={frei} heute={heute} gruppen={gruppen} eintraegeJePerson={eintraegeJePerson}
                  konflikte={konflikte} aufgaben={raster.aufgaben} projekte={raster.projekte} planen={darfPlanen}
                  gedimmt={gedimmt} vorschau={vorschau} onOeffnen={oeffnen} onLoeschen={loeschen} onGroesse={groesse}
                  infos={infos} infoBearbeitbar={darfPlanen && raster.info_bearbeitbar} onInfo={infoSetzen}
                  tagesfreigaben={tagesfreigaben}
                  freigabeName={raster.freigabe_name}
                  freigabeStufen={raster.freigabe_stufen} onFreigabe={freigabeSetzen}
                />
              )}
              <Legende projekte={Object.values(raster.projekte)} />
            </section>
            {darfPlanen && (
              <Palette
                daten={palette} heute={heute} modus={e.paletteModus} projektId={e.paletteProjekt} suche={suche}
                projekte={optionen?.projekte ?? []}
                onModus={(m) => setE({ paletteModus: m })}
                onProjekt={(id) => setE({ paletteProjekt: id })}
                onSuche={setSuche}
                onEinteilen={(aufgabe) => setDialog({ art: "neu-einteilung", aufgabe, projekt: palette?.projekte[aufgabe.projekt_id] })}
                onAbwesenheit={() => setDialog({ art: "neu-abwesenheit" })}
              />
            )}
          </div>
          <DragOverlay dropAnimation={null}>
            {ziehen ? <div className="tp-ziehbild">{ziehTitel}</div> : null}
          </DragOverlay>
        </DndContext>
      )}

      {dialog && raster && (
        <BearbeitenDialog
          eintrag={bearbeitenEintrag}
          aufgabe={dialogAufgabe}
          personen={einteilbarePersonen(einteilbar, bearbeitenEintrag, raster.personen)}
          vorgabeDatum={spalten.includes(heute) ? heute : spalten[0]}
          onSchliessen={() => setDialog(null)}
          onLoeschen={bearbeitenEintrag ? () => { loeschen(bearbeitenEintrag); setDialog(null); } : undefined}
          onSpeichern={(werte) => {
            setDialog(null);
            if (dialog.art === "bearbeiten") {
              const x = dialog.eintrag;
              const aenderung: { person_id?: number; von?: string; bis?: string } = {};
              if (werte.person_id !== x.person_id) aenderung.person_id = werte.person_id;
              if (werte.von !== x.von || werte.bis !== x.bis) Object.assign(aenderung, { von: werte.von, bis: werte.bis });
              if (Object.keys(aenderung).length) aendern(x, aenderung);
            } else if (dialog.art === "neu-einteilung") {
              einteilen(dialog.aufgabe, dialog.projekt, werte.person_id, werte.von, werte.bis);
            } else {
              abwesenheitAnlegen(werte.person_id, werte.von, werte.bis);
            }
          }}
        />
      )}
      {bestaetigung.dialog}
    </div>
  );
}

function einteilbarePersonen(einteilbar: Person[], eintrag: Eintrag | null, alle: Person[]) {
  if (!eintrag || einteilbar.some((p) => p.id === eintrag.person_id)) return einteilbar;
  const eigene = alle.find((p) => p.id === eintrag.person_id);
  return eigene ? [eigene, ...einteilbar] : einteilbar;
}

function Legende({ projekte }: { projekte: Projekt[] }) {
  return (
    <div className="tp-legende legende">
      {projekte.map((p) => (
        <span key={p.id} className={`pf-${p.farbe}`}><i className="tp-legende__projekt" />{p.name}</span>
      ))}
      <span><i className="tp-legende__abwesend" />{t("abwesend")}</span>
      <span><i style={{ background: "var(--feiertag)" }} />{t("feiertag")}</span>
      <span><i className="tp-legende__frei" />{t("feiertag_im_balken")}</span>
      <span><i className="tp-legende__konflikt" />{t("doppelt_belegt")}</span>
      <span><i className="tp-legende__platzhalter" />{t("platzhalter_ohne_konto")}</span>
    </div>
  );
}
