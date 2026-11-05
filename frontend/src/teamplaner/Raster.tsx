import { useDraggable, useDroppable } from "@dnd-kit/core";
import { memo, useEffect, useMemo, useRef, useState } from "react";
import { kalenderwoche, kurzDatum, kurzTag, langDatum, position, spuren, wochentag, zeitraumText, type Frei, type Position } from "./logik";
import { Avatar } from "./Avatar";
import { t } from "./texte";
import type { Aufgabe, FreigabeTag, Eintrag, Person, Projekt } from "./typen";

export interface Vorschau {
  personId: number;
  start: number;
  ende: number;
  art: "einteilung" | "abwesenheit";
}

interface Gemeinsam {
  spalten: string[];
  frei: Frei;
  heute: string;
  aufgaben: Record<string, Aufgabe>;
  projekte: Record<string, Projekt>;
  planen: boolean;
  gedimmt: (e: Eintrag) => boolean;
  onOeffnen: (e: Eintrag) => void;
  onLoeschen: (e: Eintrag) => void;
  onGroesse: (e: Eintrag, von: string, bis: string) => void;
}

interface RasterProps extends Gemeinsam {
  gruppen: { id: number; name: string; personen: Person[] }[];
  eintraegeJePerson: Map<number, Eintrag[]>;
  konflikte: Set<string>;
  vorschau: Vorschau | null;
  infos: Map<string, string>;
  infoBearbeitbar: boolean;
  onInfo: (datum: string, text: string) => void;
  /** Tagesfreigabe je Tag, null = Zeile ausgeblendet */
  tagesfreigaben: Map<string, FreigabeTag> | null;
  freigabeName: string;
  freigabeStufen: { wert: string; name: string }[];
  onFreigabe: (datum: string, stufe: string) => void;
}

export function RasterAnsicht({ infos, infoBearbeitbar, onInfo, tagesfreigaben, freigabeName, freigabeStufen, onFreigabe, ...props }: RasterProps) {
  const { spalten, frei, heute, gruppen } = props;
  const [zugeklappt, setZugeklappt] = useState<Set<number>>(new Set());
  const n = spalten.length;
  const stil = { "--spalten": n, "--spalte-min": n > 10 ? "56px" : "84px" } as React.CSSProperties;

  return (
    <div className="tp-raster" style={stil} role="region" aria-label={t("zeitplan")}>
      <div className="tp-kopf">
      <div className="tp-kopfzeile">
        <div className="tp-person tp-person--kopf">{t("person_gewerk")}</div>
        <div className="tp-tage">
          {spalten.map((d, i) => {
            const montag = i > 0 && wochentag(d) === 0;
            const istHeute = d === heute;
            return (
              <div key={d} className={`tp-tag${montag ? " tp-wochenanfang" : ""}${frei.has(d) ? " tp-frei" : ""}${istHeute ? " tp-heute" : ""}`}>
                <div className="tp-tag__wt">{kurzTag(d)}{istHeute ? t("heute_kurz") : ""}</div>
                <div className="tp-tag__datum">{kurzDatum(d)}</div>
                <div className="tp-tag__notiz" title={frei.get(d)}>
                  {frei.has(d) && frei.get(d) !== t("wochenende") ? frei.get(d) : i === 0 || montag ? t("kw", { n: kalenderwoche(d) }) : ""}
                </div>
              </div>
            );
          })}
        </div>
      </div>
      <div className="tp-infozeile">
        <div className="tp-person tp-person--kopf tp-person--info">{t("info")}</div>
        <div className="tp-tage">
          {spalten.map((d, i) => (
            <InfoZelle key={d} datum={d} text={infos.get(d) ?? ""} bearbeitbar={infoBearbeitbar}
              wochenanfang={i > 0 && wochentag(d) === 0} onInfo={onInfo} />
          ))}
        </div>
      </div>
      {tagesfreigaben && (
        <div className="tp-infozeile tp-freigabezeile">
          <div className="tp-person tp-person--kopf tp-person--info">{freigabeName}</div>
          <div className="tp-tage">
            {spalten.map((d, i) => (
              <FreigabeZelle key={d} datum={d} stufe={tagesfreigaben.get(d)?.stufe ?? ""} von={tagesfreigaben.get(d)?.von ?? ""} stufen={freigabeStufen} name={freigabeName}
                bearbeitbar={infoBearbeitbar}
                wochenanfang={i > 0 && wochentag(d) === 0} onFreigabe={onFreigabe} />
            ))}
          </div>
        </div>
      )}
      </div>
      {gruppen.map((g) => {
        const zu = zugeklappt.has(g.id);
        return (
          <section key={g.id} aria-label={g.name}>
            <button
              type="button"
              className="tp-gruppe"
              aria-expanded={!zu}
              onClick={() => setZugeklappt((alt) => {
                const neu = new Set(alt);
                if (neu.has(g.id)) neu.delete(g.id); else neu.add(g.id);
                return neu;
              })}
            >
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.6" aria-hidden="true"
                style={{ transform: zu ? "rotate(-90deg)" : undefined }}><path d="M6 9l6 6 6-6" /></svg>
              {g.name}
              <span className="tp-gruppe__anzahl">{t(g.personen.length === 1 ? "person_anzahl" : "personen_anzahl", { n: g.personen.length })}</span>
            </button>
            {!zu && g.personen.map((p) => (
              <Zeile
                key={p.id}
                {...props}
                person={p}
                eintraege={props.eintraegeJePerson.get(p.id) ?? EMPTY}
                konfliktTage={konfliktTage(props.konflikte, p.id, spalten)}
                vorschau={props.vorschau?.personId === p.id ? props.vorschau : null}
              />
            ))}
          </section>
        );
      })}
    </div>
  );
}

const EMPTY: Eintrag[] = [];

/** Büroklammer vor dem Titel, wenn die Aufgabe Dateianhänge hat. */
export function AnhangSymbol({ anzahl }: { anzahl: number }) {
  const text = anzahl === 1 ? t("anhang_eins") : t("anhaenge_anzahl", { n: anzahl });
  return (
    <svg className="tp-anhang" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4"
      strokeLinecap="round" strokeLinejoin="round" role="img" aria-label={text}>
      <title>{text}</title>
      <path d="M21 11.5l-8.6 8.6a5.5 5.5 0 0 1-7.8-7.8l8.6-8.6a3.7 3.7 0 0 1 5.2 5.2l-8.6 8.6a1.8 1.8 0 0 1-2.6-2.6l7.9-7.9" />
    </svg>
  );
}

/** Ein Tag der Info-Zeile: Freitext für alle; gelb, sobald etwas eingetragen ist. */
const InfoZelle = memo(function InfoZelle({ datum, text, bearbeitbar, wochenanfang, onInfo }: {
  datum: string; text: string; bearbeitbar: boolean; wochenanfang: boolean; onInfo: (datum: string, text: string) => void;
}) {
  const [entwurf, setEntwurf] = useState(text);
  const verwerfen = useRef(false);
  useEffect(() => setEntwurf(text), [text]);
  const klassen = `tp-info${text ? " tp-info--gesetzt" : ""}${wochenanfang ? " tp-wochenanfang" : ""}`;
  if (!bearbeitbar) {
    return <div className={klassen} title={text || undefined}>{text}</div>;
  }
  return (
    <div className={klassen}>
      <input
        type="text"
        className="tp-info__eingabe"
        value={entwurf}
        maxLength={120}
        placeholder={t("info_platzhalter")}
        aria-label={t("info_label", { datum: `${kurzTag(datum)} ${langDatum(datum)}` })}
        title={text || undefined}
        onChange={(e) => setEntwurf(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter") e.currentTarget.blur();
          if (e.key === "Escape") { verwerfen.current = true; e.currentTarget.blur(); }
        }}
        onBlur={() => {
          if (verwerfen.current) {
            verwerfen.current = false;
            setEntwurf(text);
            return;
          }
          const neu = entwurf.trim();
          if (neu !== text) onInfo(datum, neu);
        }}
      />
    </div>
  );
});

/** Ein Tag der Zeile „Tagesfreigabe“: Auswahl aus den eingestellten Stufen; ohne Stufe „keine Freigabe“ rot hinterlegt, mit Stufe grün,
 *  mit Stufe darunter dünner, wer sie gesetzt hat. Gilt für alle Tage, auch Wochenenden und Feiertage. */
const FreigabeZelle = memo(function FreigabeZelle({ datum, stufe, von, stufen, name: zeilenName, bearbeitbar, wochenanfang, onFreigabe }: {
  datum: string; stufe: string; von: string; stufen: { wert: string; name: string }[]; name: string; bearbeitbar: boolean;
  wochenanfang: boolean; onFreigabe: (datum: string, stufe: string) => void;
}) {
  const name = (stufe && stufen.find((s) => s.wert === stufe)?.name) || "";
  const klassen = `tp-info tp-freigabe${stufe ? " tp-freigabe--gesetzt" : " tp-freigabe--keine"}${bearbeitbar ? " tp-freigabe--bearbeitbar" : ""}`
    + (wochenanfang ? " tp-wochenanfang" : "");
  // Angezeigt wird immer der Text (darf in schmalen Spalten umbrechen); zum Bearbeiten liegt die native
  // Auswahl unsichtbar darüber – ein <select> selbst würde „keine Freigabe“ abschneiden.
  return (
    <div className={klassen}>
      <span className="tp-freigabe__stufe" title={name || t("freigabe_keine")}>{name || t("freigabe_keine")}</span>
      {stufe && von && <span className="tp-freigabe__von" title={von}>{von}</span>}
      {bearbeitbar && (
        <select className="tp-freigabe__wahl" value={stufe}
          aria-label={t("freigabe_label", { name: zeilenName, datum: `${kurzTag(datum)} ${langDatum(datum)}` })}
          onChange={(e) => onFreigabe(datum, e.target.value)}>
          <option value="">{t("freigabe_keine")}</option>
          {stufen.map((s) => <option key={s.wert} value={s.wert}>{s.name}</option>)}
        </select>
      )}
    </div>
  );
});

function konfliktTage(konflikte: Set<string>, personId: number, spalten: string[]): string {
  // als String, damit memo() bei unveränderten Konflikten nicht neu rendert
  return spalten.filter((d) => konflikte.has(`${personId}:${d}`)).join(",");
}

interface ZeileProps extends Gemeinsam {
  person: Person;
  eintraege: Eintrag[];
  konfliktTage: string;
  vorschau: Vorschau | null;
}

const Zeile = memo(function Zeile(props: ZeileProps) {
  const { person, eintraege, spalten, frei, heute, vorschau, planen } = props;
  const konflikte = useMemo(() => new Set(props.konfliktTage ? props.konfliktTage.split(",") : []), [props.konfliktTage]);
  const bearbeitbar = planen && person.einteilbar;

  const positioniert = useMemo(
    () =>
      eintraege
        .map((e) => ({ eintrag: e, position: position(e.von, e.bis, spalten) }))
        .filter((x): x is { eintrag: Eintrag; position: Position } => x.position !== null),
    [eintraege, spalten],
  );
  const spurListe = useMemo(() => spuren(positioniert), [positioniert]);

  return (
    <div className={`tp-zeile${person.ich ? " tp-zeile--ich" : ""}${person.archiviert ? " tp-zeile--archiviert" : ""}`}>
      <div className="tp-person">
        <Avatar person={person} />
        <div className="tp-person__text">
          <div className="tp-person__name">{person.name}{person.ich ? t("ich") : ""}</div>
          <div className="tp-person__gewerk">{person.platzhalter ? t("platzhalter_kein_konto") : person.gewerke.join(" · ")}</div>
          {person.archiviert && <span className="badge">{t("archiviert")}</span>}
          {konflikte.size > 0 && (
            <span className="badge badge--warn">{t(konflikte.size === 1 ? "tag_doppelt" : "tage_doppelt", { n: konflikte.size })}</span>
          )}
        </div>
      </div>
      <div className="tp-flaeche">
        <div className="tp-hintergrund" aria-hidden="true">
          {spalten.map((d, i) => (
            <Zelle key={d} personId={person.id} spalte={i} datum={d} aktiv={bearbeitbar && person.auswaehlbar}
              klassen={[
                i > 0 && wochentag(d) === 0 ? "tp-wochenanfang" : "",
                frei.has(d) ? "tp-frei" : "",
                d === heute ? "tp-heute" : "",
                konflikte.has(d) ? "tp-konflikt" : "",
              ].join(" ")}
            />
          ))}
        </div>
        {vorschau && (
          <div className={`tp-vorschau tp-vorschau--${vorschau.art}`}
            style={{ gridColumn: `${vorschau.start + 1} / ${vorschau.ende + 2}` }} />
        )}
        {konflikte.size > 0 && (
          <div className="tp-konfliktmarken" aria-hidden="true">
            {spalten.map((d) => <span key={d} className={konflikte.has(d) ? "an" : undefined} />)}
          </div>
        )}
        <div className="tp-spuren">
          {spurListe.length === 0 && <div className="tp-spur tp-spur--leer" />}
          {spurListe.map((spur, i) => (
            <div key={i} className="tp-spur">
              {spur.map(({ eintrag, position: pos }) => (
                <Balken key={`${eintrag.art}:${eintrag.id}`} {...props} eintrag={eintrag} pos={pos} bearbeitbar={bearbeitbar} />
              ))}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
});

const Zelle = memo(function Zelle({ personId, spalte, datum, aktiv, klassen }: {
  personId: number; spalte: number; datum: string; aktiv: boolean; klassen: string;
}) {
  const { setNodeRef, isOver } = useDroppable({ id: `z:${personId}:${spalte}`, data: { personId, spalte, datum }, disabled: !aktiv });
  return <div ref={setNodeRef} className={`tp-zelle ${klassen}${isOver ? " tp-zelle--ueber" : ""}`} />;
});

interface BalkenProps extends Gemeinsam {
  eintrag: Eintrag;
  pos: Position;
  bearbeitbar: boolean;
  person: Person;
}

function Balken({ eintrag, pos, bearbeitbar, spalten, frei, aufgaben, projekte, gedimmt, onOeffnen, onLoeschen, onGroesse, person }: BalkenProps) {
  const [groesse, setGroesse] = useState<{ start: number; ende: number } | null>(null);
  const ref = useRef<HTMLDivElement | null>(null);
  const geradeGezogen = useRef(false);
  const griff = useRef(0); // Spalte innerhalb des Balkens, an der gegriffen wurde
  const { attributes, listeners, setNodeRef, isDragging } = useDraggable({
    id: `${eintrag.art}:${eintrag.id}`,
    data: { typ: eintrag.art, eintrag, position: pos, griff },
    disabled: !bearbeitbar || eintrag.id < 0,
  });

  const start = groesse?.start ?? pos.start;
  const ende = groesse?.ende ?? pos.ende;
  const span = ende - start + 1;
  const aufgabe = eintrag.art === "einteilung" ? aufgaben[eintrag.aufgabe_id] : undefined;
  const projekt = aufgabe ? projekte[aufgabe.projekt_id] : undefined;
  const titel = eintrag.art === "abwesenheit" ? t("abwesend") : aufgabe?.titel ?? "…";
  const anzahlTage = eintrag.art === "abwesenheit"
    ? spalten.slice(start, ende + 1).length
    : 0;
  const unterzeile = eintrag.art === "abwesenheit"
    ? t(anzahlTage === 1 ? "tag_anzahl" : "tage_anzahl", { n: anzahlTage })
    : [projekt?.name, aufgabe?.eltern].filter(Boolean).join(" › ");
  // Unteraufgaben mit Pfad der Zugehörigkeit („Projekt › Hauptaufgabe › Unteraufgabe“)
  const label = `${aufgabe?.eltern ? `${aufgabe.eltern} › ` : ""}${titel}, ${person.name}, ${zeitraumText(eintrag.von, eintrag.bis)}`;

  // Feiertage innerhalb des Balkens schraffieren (eintägig zählt, mehrtägig nicht)
  const freiSegmente = [];
  for (let c = start; c <= ende; c += 1) {
    if (frei.has(spalten[c])) {
      freiSegmente.push(
        <span key={c} className="tp-balken__frei" title={frei.get(spalten[c])}
          style={{ left: `${((c - start) / span) * 100}%`, width: `${100 / span}%` }} />,
      );
    }
  }

  const groesseAendern = (seite: "links" | "rechts") => (e: React.PointerEvent) => {
    e.stopPropagation();
    e.preventDefault();
    const flaeche = ref.current?.closest(".tp-flaeche")?.getBoundingClientRect();
    if (!flaeche) return;
    const breite = flaeche.width / spalten.length;
    let aktuell = { start: pos.start, ende: pos.ende };
    const bewegen = (ev: PointerEvent) => {
      const spalte = Math.max(0, Math.min(spalten.length - 1, Math.floor((ev.clientX - flaeche.left) / breite)));
      aktuell = seite === "rechts" ? { start: pos.start, ende: Math.max(spalte, pos.start) } : { start: Math.min(spalte, pos.ende), ende: pos.ende };
      setGroesse(aktuell);
    };
    const ende_ = () => {
      window.removeEventListener("pointermove", bewegen);
      window.removeEventListener("pointerup", ende_);
      // Der folgende click-Event gehört zum Ziehen und soll keinen Dialog öffnen
      geradeGezogen.current = true;
      window.setTimeout(() => (geradeGezogen.current = false), 0);
      setGroesse(null);
      if (aktuell.start !== pos.start || aktuell.ende !== pos.ende) {
        onGroesse(
          eintrag,
          pos.linksAbgeschnitten && aktuell.start === pos.start ? eintrag.von : spalten[aktuell.start],
          pos.rechtsAbgeschnitten && aktuell.ende === pos.ende ? eintrag.bis : spalten[aktuell.ende],
        );
      }
    };
    window.addEventListener("pointermove", bewegen);
    window.addEventListener("pointerup", ende_);
  };

  const klassen = [
    "tp-balken",
    eintrag.art === "abwesenheit" ? "tp-balken--abwesend" : `pf-${projekt?.farbe ?? "grau"}`,
    pos.linksAbgeschnitten ? "tp-balken--links-offen" : "",
    pos.rechtsAbgeschnitten ? "tp-balken--rechts-offen" : "",
    isDragging ? "tp-balken--zieht" : "",
    gedimmt(eintrag) ? "tp-balken--gedimmt" : "",
    bearbeitbar ? "tp-balken--bearbeitbar" : "",
    eintrag.id < 0 ? "tp-balken--speichert" : "",
  ].join(" ");
  const stil = { gridColumn: `${start + 1} / span ${span}` };
  const inhalt = (
    <>
      {freiSegmente}
      <span className="tp-balken__titel">{aufgabe && aufgabe.anhaenge > 0 && <AnhangSymbol anzahl={aufgabe.anhaenge} />}{titel}</span>
      {unterzeile && <span className="tp-balken__unter">{unterzeile}</span>}
    </>
  );

  if (!bearbeitbar) {
    if (aufgabe) {
      return (
        <a href={aufgabe.url} className={klassen} style={stil} title={label} aria-label={label}>
          {inhalt}
        </a>
      );
    }
    return <div className={klassen} style={stil} title={label} aria-label={label}>{inhalt}</div>;
  }

  return (
    <div
      ref={(el) => { setNodeRef(el); ref.current = el; }}
      className={klassen}
      style={stil}
      {...attributes}
      {...listeners}
      onPointerDown={(e) => {
        const r = e.currentTarget.getBoundingClientRect();
        griff.current = Math.max(0, Math.min(span - 1, Math.floor((e.clientX - r.left) / (r.width / span))));
        listeners?.onPointerDown?.(e);
      }}
      role="button"
      tabIndex={0}
      aria-label={t("balken_hilfe", { label })}
      title={label}
      onClick={() => { if (!geradeGezogen.current) onOeffnen(eintrag); }}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") { e.preventDefault(); onOeffnen(eintrag); }
        if (e.key === "Delete" || e.key === "Backspace") { e.preventDefault(); onLoeschen(eintrag); }
      }}
    >
      {inhalt}
      {!pos.linksAbgeschnitten && <span className="tp-griff tp-griff--links" onPointerDown={groesseAendern("links")} aria-hidden="true" />}
      {!pos.rechtsAbgeschnitten && <span className="tp-griff tp-griff--rechts" onPointerDown={groesseAendern("rechts")} aria-hidden="true" />}
      <button type="button" className="tp-balken__x" aria-label={t("entfernen_von", { titel })} title={t("entfernen")}
        onPointerDown={(e) => e.stopPropagation()}
        onClick={(e) => { e.stopPropagation(); onLoeschen(eintrag); }}>×</button>
    </div>
  );
}
