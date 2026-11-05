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
import { t } from "../lib/texte";
import { erweiterungen } from "./erweiterungen";
import { hatFormatierung, siehtNachMarkdownAus } from "./markdown";

// Nach so langer Tipp-Pause wird gespeichert, damit bei langen Texten nichts verloren geht
const PAUSE_MS = 3000;

interface Knopf {
  label: string;
  titel: string;
  aktion: (e: Editor) => void;
  aktiv: (e: Editor) => boolean;
}

function knoepfe(ebene: 2 | 3): Knopf[] {
  return [
    { label: "B", titel: t("fett"), aktion: (e) => e.chain().focus().toggleBold().run(), aktiv: (e) => e.isActive("bold") },
    { label: "I", titel: t("kursiv"), aktion: (e) => e.chain().focus().toggleItalic().run(), aktiv: (e) => e.isActive("italic") },
    { label: "H", titel: t("zwischenueberschrift"), aktion: (e) => e.chain().focus().toggleHeading({ level: ebene }).run(), aktiv: (e) => e.isActive("heading") },
    { label: t("liste"), titel: t("aufzaehlung"), aktion: (e) => e.chain().focus().toggleBulletList().run(), aktiv: (e) => e.isActive("bulletList") },
    { label: t("nummern"), titel: t("nummerierte_liste"), aktion: (e) => e.chain().focus().toggleOrderedList().run(), aktiv: (e) => e.isActive("orderedList") },
    {
      label: t("link"),
      titel: t("link_einfuegen"),
      aktion: (e) => {
        const alt = e.getAttributes("link").href as string | undefined;
        const url = window.prompt(t("link_frage"), alt ?? "https://");
        if (url === null) return;
        if (url === "") e.chain().focus().unsetLink().run();
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

  const editor: Editor = new Editor({
    element: flaeche,
    content: feld.value,
    contentType: markdown ? "markdown" : "html",
    extensions: erweiterungen(markdown, feld.placeholder || t("beschreibung")),
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
      feld.dispatchEvent(new Event("input", { bubbles: true }));
      window.clearTimeout(pause);
      pause = window.setTimeout(speichern, PAUSE_MS);
    },
    onBlur: speichern,
  });
  // Fenster wird geschlossen oder gewechselt: noch schnell speichern
  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "hidden" && halter.isConnected) speichern();
  });

  const liste = knoepfe(markdown ? 2 : 3).map((k) => {
    const b = document.createElement("button");
    b.type = "button";
    b.textContent = k.label;
    b.title = k.titel;
    b.addEventListener("click", () => k.aktion(editor));
    leiste.append(b);
    return { b, k };
  });
  const aktualisieren = () => liste.forEach(({ b, k }) => b.setAttribute("aria-pressed", String(k.aktiv(editor))));
  editor.on("selectionUpdate", aktualisieren);
  editor.on("transaction", aktualisieren);
  if (halter.dataset.fokus !== undefined) editor.commands.focus("end");
}

function init(wurzel: ParentNode) {
  wurzel.querySelectorAll<HTMLElement>("[data-editor]").forEach(einrichten);
}

init(document);
document.addEventListener("htmx:load", (e) => init(e.target as ParentNode));
