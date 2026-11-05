import type { Person } from "./typen";

/** Foto oder Initialen; Platzhalter gestrichelt, Archivierte blass. */
export function Avatar({ person, groesse }: { person: Pick<Person, "id" | "initialen" | "foto" | "platzhalter" | "archiviert">; groesse?: "klein" }) {
  const klassen = [
    "avatar",
    groesse ? `avatar--${groesse}` : "",
    person.platzhalter ? "avatar--platzhalter" : `av-${person.id % 8}`,
    person.archiviert ? "avatar--archiviert" : "",
  ].join(" ");
  if (person.foto && !person.platzhalter) {
    return <img className={`${klassen} avatar--foto`} src={person.foto} alt="" aria-hidden="true" />;
  }
  return <span className={klassen} aria-hidden="true">{person.initialen}</span>;
}
