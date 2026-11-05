import { useState } from "react";
import { kurzDatum, kurzTag, type Frei } from "./logik";
import { Avatar } from "./Avatar";
import { AnhangSymbol } from "./Raster";
import { t } from "./texte";
import type { Aufgabe, FreigabeTag, Eintrag, Person, Projekt } from "./typen";

interface Props {
  spalten: string[];
  frei: Frei;
  infos: Map<string, string>;
  /** Tagesfreigabe je Tag, null = Zeile ausgeblendet */
  tagesfreigaben: Map<string, FreigabeTag> | null;
  freigabeName: string;
  heute: string;
  gruppen: { id: number; name: string; personen: Person[] }[];
  eintraegeJePerson: Map<number, Eintrag[]>;
  aufgaben: Record<string, Aufgabe>;
  projekte: Record<string, Projekt>;
}

/** Lesekalender fürs Smartphone: ein Tag, darunter alle Personen mit ihren Karten. */
export function Tagesansicht({ spalten, frei, infos, tagesfreigaben, freigabeName, heute, gruppen, eintraegeJePerson, aufgaben, projekte }: Props) {
  const [tag, setTag] = useState(spalten.includes(heute) ? heute : spalten[0]);
  const aktiv = spalten.includes(tag) ? tag : spalten[0];

  return (
    <div className="tp-tagesansicht">
      <div className="tp-tageswahl" role="group" aria-label={t("tag_waehlen")}>
        {spalten.map((d) => (
          <button key={d} type="button" aria-pressed={d === aktiv} onClick={() => setTag(d)}
            className={`${frei.has(d) ? "tp-frei" : ""}${d === heute ? " tp-heute" : ""}${infos.has(d) ? " tp-info-punkt" : ""}`}>
            <span>{kurzTag(d)}</span>
            <span className="mono">{kurzDatum(d)}</span>
          </button>
        ))}
      </div>
      {frei.has(aktiv) && <div className="meldung">{t("feiertag_hinweis", { name: frei.get(aktiv) ?? "" })}</div>}
      {infos.has(aktiv) && <div className="meldung tp-info--gesetzt">{t("info")}: {infos.get(aktiv)}</div>}
      {tagesfreigaben && <FreigabeMeldung tag={tagesfreigaben.get(aktiv)} name={freigabeName} />}
      {gruppen.map((g) => (
        <section key={g.id} className="karte">
          <h2 className="tp-tagesansicht__gruppe">{g.name}</h2>
          {g.personen.map((p) => {
            const eintraege = (eintraegeJePerson.get(p.id) ?? []).filter((e) => e.von <= aktiv && e.bis >= aktiv);
            return (
              <div key={p.id} className={`tp-tagesansicht__zeile${p.ich ? " tp-zeile--ich" : ""}`}>
                <div className="person">
                  <Avatar person={p} groesse="klein" />
                  <span className="person__name">{p.name}{p.ich ? t("ich") : ""}</span>
                </div>
                <div className="tp-tagesansicht__karten">
                  {eintraege.length === 0 && <span className="gedaempft klein">–</span>}
                  {eintraege.map((e) => {
                    if (e.art === "abwesenheit") {
                      return <span key={`a${e.id}`} className="tp-balken tp-balken--abwesend tp-balken--karte">{t("abwesend")}</span>;
                    }
                    const a = aufgaben[e.aufgabe_id];
                    const projekt = a ? projekte[a.projekt_id] : undefined;
                    const zaehltNicht = frei.has(aktiv) && e.von !== e.bis;
                    return (
                      <a key={`e${e.id}`} href={a?.url} className={`tp-balken tp-balken--karte pf-${projekt?.farbe ?? "grau"}${zaehltNicht ? " tp-balken--feiertag" : ""}`}>
                        <span className="tp-balken__titel">{a && a.anhaenge > 0 && <AnhangSymbol anzahl={a.anhaenge} />}{a?.titel}</span>
                        <span className="tp-balken__unter">{projekt?.name}{zaehltNicht ? t("feiertag_zaehlt_nicht") : ""}</span>
                      </a>
                    );
                  })}
                </div>
              </div>
            );
          })}
        </section>
      ))}
    </div>
  );
}

/** Tagesfreigabe des gewählten Tags: „keine Freigabe“ in Rot oder die Stufe mit dem Namen darunter. */
function FreigabeMeldung({ tag, name }: { tag: FreigabeTag | undefined; name: string }) {
  if (!tag?.stufe) {
    return <div className="meldung tp-freigabe--keine">{name}: {t("freigabe_keine")}</div>;
  }
  return (
    <div className="meldung tp-freigabe--gesetzt">
      {name}: {tag.name}
      {tag.von && <span className="tp-freigabe__von">{tag.von}</span>}
    </div>
  );
}
