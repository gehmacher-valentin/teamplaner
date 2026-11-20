/**
 * Formatierter Text mit Tiptap: Aufgabenbeschreibungen (gespeichert als HTML) und Notizen
 * (gespeichert als Markdown). Derselbe Editor, nur mit anderer Ein- und Ausgabe.
 *
 * <div data-editor="id" data-format="html|markdown"> ersetzt das Textfeld mit dieser ID. Der Inhalt
 * wird beim Tippen zurückgeschrieben; gespeichert wird beim Verlassen und kurz nach dem letzten
 * Tippen (change-Ereignis am Textfeld, hx-trigger="change"). Der Server bereinigt alles (nh3).
 * Eingefügtes Markdown wird zu Formatierung, Markdown-Kürzel beim Tippen ebenso (Eingaberegeln).
 */
import { Editor } from "@tiptap/core";
import { eingeben } from "../lib/dialog";
import { t } from "../lib/texte";
import Collaboration from "@tiptap/extension-collaboration";
import { erweiterungen } from "./erweiterungen";
import { MARKERFARBEN, SCHRIFTFARBEN } from "./farben";
import { gemeinsamVorbereiten } from "./gemeinsam";
import { hatFormatierung, siehtNachMarkdownAus } from "./markdown";

// Nach so langer Tipp-Pause wird gespeichert, damit bei langen Texten nichts verloren geht
const PAUSE_MS = 3000;

interface Knopf {
  label: string;
  titel: string;
  aktion: (e: Editor, knopf: HTMLButtonElement) => void;
  aktiv: (e: Editor) => boolean;
  klasse?: string;
}

type FarbArt = "schriftfarbe" | "marker";

/** Kleine Farbauswahl unter dem Knopf; Klick daneben oder Esc schließt sie. */
function farbwahl(e: Editor, knopf: HTMLButtonElement, art: FarbArt) {
  const leiste = knopf.parentElement!;
  const offen = leiste.querySelector<HTMLElement>(".editor__farbwahl");
  offen?.dispatchEvent(new Event("schliessen"));
  if (offen?.dataset.art === art) return;

  const farben = art === "schriftfarbe" ? SCHRIFTFARBEN : MARKERFARBEN;
  const aktuell = e.getAttributes(art).farbe as string | undefined;
  const wahl = document.createElement("div");
  wahl.className = `editor__farbwahl editor__farbwahl--${art}`;
  wahl.dataset.art = art;
  wahl.setAttribute("role", "group");
  wahl.setAttribute("aria-label", t(art));
  wahl.style.left = `${knopf.offsetLeft}px`;
  const setzen = (farbe: string | null) => {
    schliessen();
    if (art === "schriftfarbe") e.commands.schriftfarbeSetzen(farbe);
    else e.commands.markerSetzen(farbe);
  };
  for (const farbe of farben) {
    const b = document.createElement("button");
    b.type = "button";
    b.className = "editor__farbfeld";
    b.dataset.farbe = farbe;
    b.title = t(`farbe_${farbe}`);
    b.setAttribute("aria-label", t(`farbe_${farbe}`));
    b.setAttribute("aria-pressed", String(farbe === aktuell));
    b.textContent = art === "schriftfarbe" ? "A" : "";
    b.addEventListener("click", () => setzen(farbe));
    wahl.append(b);
  }
  const keine = document.createElement("button");
  keine.type = "button";
  keine.className = "editor__farbe-keine";
  keine.textContent = t("farbe_keine");
  keine.addEventListener("click", () => setzen(null));
  wahl.append(keine);

  const draussen = (ev: MouseEvent) => {
    if (!wahl.contains(ev.target as Node) && ev.target !== knopf) schliessen();
  };
  const taste = (ev: KeyboardEvent) => {
    if (ev.key !== "Escape") return;
    ev.stopPropagation();
    schliessen();
    knopf.focus();
  };
  function schliessen() {
    wahl.remove();
    knopf.setAttribute("aria-expanded", "false");
    document.removeEventListener("mousedown", draussen, true);
    wahl.removeEventListener("keydown", taste);
  }
  wahl.addEventListener("schliessen", schliessen);
  wahl.addEventListener("keydown", taste);
  document.addEventListener("mousedown", draussen, true);
  leiste.append(wahl);
  knopf.setAttribute("aria-expanded", "true");
  wahl.querySelector<HTMLButtonElement>('[aria-pressed="true"]')?.focus() ?? wahl.querySelector("button")!.focus();
}

function knoepfe(ebene: 2 | 3): Knopf[] {
  return [
    { label: "B", titel: t("fett"), aktion: (e) => e.chain().focus().toggleBold().run(), aktiv: (e) => e.isActive("bold") },
    { label: "I", titel: t("kursiv"), aktion: (e) => e.chain().focus().toggleItalic().run(), aktiv: (e) => e.isActive("italic") },
    { label: "A", titel: t("schriftfarbe"), klasse: "editor__knopf--schriftfarbe", aktion: (e, k) => farbwahl(e, k, "schriftfarbe"), aktiv: (e) => e.isActive("schriftfarbe") },
    { label: "ab", titel: t("marker"), klasse: "editor__knopf--marker", aktion: (e, k) => farbwahl(e, k, "marker"), aktiv: (e) => e.isActive("marker") },
    { label: "H", titel: t("zwischenueberschrift"), aktion: (e) => e.chain().focus().toggleHeading({ level: ebene }).run(), aktiv: (e) => e.isActive("heading") },
    { label: t("liste"), titel: t("aufzaehlung"), aktion: (e) => e.chain().focus().toggleBulletList().run(), aktiv: (e) => e.isActive("bulletList") },
    { label: t("nummern"), titel: t("nummerierte_liste"), aktion: (e) => e.chain().focus().toggleOrderedList().run(), aktiv: (e) => e.isActive("orderedList") },
    {
      label: t("link"),
      titel: t("link_einfuegen"),
      aktion: async (e) => {
        const alt = e.getAttributes("link").href as string | undefined;
        const url = await eingeben(t("link_frage"), alt ?? "https://");
        if (url === null) return e.commands.focus();
        if (url === "") e.chain().focus().extendMarkRange("link").unsetLink().run();
        else e.chain().focus().extendMarkRange("link").setLink({ href: url }).run();
      },
      aktiv: (e) => e.isActive("link"),
    },
  ];
}

function einrichten(halter: HTMLElement) {
  const feld = document.getElementById(halter.dataset.editor!) as HTMLTextAreaElement | null;
  if (!feld || halter.dataset.editorAktiv) return;
  halter.dataset.editorAktiv = "1";
  feld.hidden = true;
  const markdown = halter.dataset.format === "markdown";

  halter.classList.add("editor");
  const leiste = document.createElement("div");
  leiste.className = "editor__leiste";
  leiste.setAttribute("role", "toolbar");
  leiste.setAttribute("aria-label", t("formatierung"));
  const flaeche = document.createElement("div");
  flaeche.className = markdown ? "editor__flaeche markdown" : "editor__flaeche";
  halter.append(leiste, flaeche);

  const name = feld.getAttribute("aria-label")
    || (feld.getAttribute("aria-labelledby") && document.getElementById(feld.getAttribute("aria-labelledby")!)?.textContent)
    || t("beschreibung");
  let gespeichert = feld.value;
  let pause: number | undefined;
  const speichern = () => {
    window.clearTimeout(pause);
    if (feld.value === gespeichert) return;
    gespeichert = feld.value;
    feld.dispatchEvent(new Event("change", { bubbles: true }));
  };

  // Notizen: gemeinsam bearbeiten (gemeinsam.ts), der Inhalt kommt dann aus dem Yjs-Dokument
  const gemeinsam = halter.dataset.gemeinsam ? gemeinsamVorbereiten(halter.dataset.gemeinsam, feld) : null;
  const editor: Editor = new Editor({
    element: flaeche,
    content: gemeinsam ? undefined : feld.value,
    contentType: markdown ? "markdown" : "html",
    extensions: [
      ...erweiterungen(markdown, feld.placeholder || t("beschreibung"), Boolean(gemeinsam)),
      ...(gemeinsam ? [Collaboration.configure({ document: gemeinsam.doc, field: "inhalt" })] : []),
    ],
    editable: !feld.disabled && !feld.readOnly,
    editorProps: {
      attributes: { "aria-label": name, role: "textbox", "aria-multiline": "true" },
      handlePaste: (_view, event) => {
        const text = event.clipboardData?.getData("text/plain") ?? "";
        const html = event.clipboardData?.getData("text/html") ?? "";
        if (!text || hatFormatierung(html) || !siehtNachMarkdownAus(text)) return false;
        editor.commands.insertContent(text, { contentType: "markdown" });
        return true;
      },
    },
    onUpdate: ({ editor: e }) => {
      feld.value = e.isEmpty ? "" : markdown ? e.getMarkdown() : e.getHTML();
      if (gemeinsam) return; // speichert selbst
      feld.dispatchEvent(new Event("input", { bubbles: true }));
      window.clearTimeout(pause);
      pause = window.setTimeout(speichern, PAUSE_MS);
    },
    onBlur: () => { if (!gemeinsam) speichern(); },
  });
  // Fenster wird geschlossen oder gewechselt: noch schnell speichern
  document.addEventListener("visibilitychange", () => {
    if (!gemeinsam && document.visibilityState === "hidden" && halter.isConnected) speichern();
  });
  if (!editor.isEditable) leiste.hidden = true;

  const liste = knoepfe(markdown ? 2 : 3).map((k) => {
    const b = document.createElement("button");
    b.type = "button";
    b.textContent = k.label;
    b.title = k.titel;
    if (k.klasse) {
      b.className = k.klasse;
      b.setAttribute("aria-label", k.titel);
      b.setAttribute("aria-haspopup", "true");
      b.setAttribute("aria-expanded", "false");
    }
    b.addEventListener("click", () => k.aktion(editor, b));
    leiste.append(b);
    return { b, k };
  });
  const aktualisieren = () => liste.forEach(({ b, k }) => b.setAttribute("aria-pressed", String(k.aktiv(editor))));
  editor.on("selectionUpdate", aktualisieren);
  editor.on("transaction", aktualisieren);
  if (halter.dataset.fokus !== undefined) editor.commands.focus("end");
  gemeinsam?.starten(editor);
}

function init(wurzel: ParentNode) {
  wurzel.querySelectorAll<HTMLElement>("[data-editor]").forEach(einrichten);
}

init(document);
document.addEventListener("htmx:load", (e) => init(e.target as ParentNode));
