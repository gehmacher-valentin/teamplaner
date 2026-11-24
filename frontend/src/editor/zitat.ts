/** Zitat setzen und wieder entfernen (Knopf in der Werkzeugleiste). */
import type { Editor } from "@tiptap/core";
import type { Transaction } from "@tiptap/pm/state";
import { findWrapping, liftTarget } from "@tiptap/pm/transform";

const LISTEN = new Set(["listItem", "bulletList", "orderedList"]);

/** Alle Zitate auflösen, die die Markierung berührt, auch mehrere und verschachtelte. */
function aufloesen(tr: Transaction) {
  const stellen: number[] = [];
  tr.doc.nodesBetween(tr.selection.from, tr.selection.to, (knoten, pos) => {
    if (knoten.type.name === "blockquote") stellen.push(pos);
  });
  // Von hinten (innen) nach vorne, so bleiben die vorderen Stellen gültig
  for (const pos of stellen.reverse()) {
    const knoten = tr.doc.nodeAt(pos)!;
    const bereich = tr.doc.resolve(pos + 1).blockRange(tr.doc.resolve(pos + knoten.nodeSize - 1), (n) => n === knoten);
    const ziel = bereich && liftTarget(bereich);
    if (bereich && ziel !== null && ziel !== undefined) tr.lift(bereich, ziel);
  }
}

/** Alles Markierte steht in Zitaten. Leere Absätze zählen nicht, z. B. der am Ende angehängte bei Strg+A. */
export function imZitat(e: Editor) {
  const { doc, selection } = e.state;
  let drin = 0;
  let draussen = 0;
  doc.nodesBetween(selection.from, selection.to, (knoten, pos) => {
    if (!knoten.isTextblock) return;
    const stelle = doc.resolve(pos);
    const zitat = Array.from({ length: stelle.depth + 1 }, (_, d) => stelle.node(d)).some((n) => n.type.name === "blockquote");
    if (zitat) drin++;
    else if (knoten.content.size) draussen++;
  });
  return drin > 0 && draussen === 0;
}

/**
 * Steht die Markierung im Zitat, wird wieder normaler Text daraus, sonst wird sie zu einem Zitat.
 * Anders als bei toggleBlockquote entstehen bei gemischter Auswahl keine verschachtelten Zitate, und
 * Listen kommen als Ganzes hinein und heraus, statt ihre Punkte zu verlieren.
 */
export function zitatUmschalten(e: Editor) {
  const aktiv = imZitat(e);
  return e
    .chain()
    .focus()
    .command(({ tr }) => {
      aufloesen(tr);
      if (aktiv) return true;
      const { $from, $to } = tr.selection;
      const bereich = $from.blockRange($to, (n) => !LISTEN.has(n.type.name));
      const huelle = bereich && findWrapping(bereich, tr.doc.type.schema.nodes.blockquote);
      if (bereich && huelle) tr.wrap(bereich, huelle);
      return true;
    })
    .run();
}
