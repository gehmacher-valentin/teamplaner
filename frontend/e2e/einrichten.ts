// Vor dem ersten Test: jede Rolle einmal anmelden und die Sitzung speichern. Admin und
// Bereichsleitung richten dabei die Zwei-Faktor-Anmeldung ein (nur mit frischen Demodaten möglich).
import { chromium, type FullConfig } from "@playwright/test";
import { mkdir } from "node:fs/promises";
import { dirname } from "node:path";
import { anmelden } from "../werkzeuge/anmeldung.mjs";
import { KONTEN, zustand, type Rolle } from "./hilfen";

export default async function einrichten(config: FullConfig) {
  const { baseURL, launchOptions } = config.projects[0].use;
  const browser = await chromium.launch(launchOptions);
  for (const rolle of Object.keys(KONTEN) as Rolle[]) {
    const kontext = await browser.newContext({ locale: "de-AT" });
    const seite = await kontext.newPage();
    await anmelden(seite, baseURL, KONTEN[rolle]);
    // Nach dem Einrichten des zweiten Faktors stehen dort die Ersatzcodes: erst die nächste Seite zeigt, ob es geklappt hat
    await seite.goto(`${baseURL}/start/`);
    if (/\/anmelden\/|\/zwei-faktor\//.test(seite.url())) throw new Error(`Anmeldung als ${rolle} fehlgeschlagen: ${seite.url()}`);
    await mkdir(dirname(zustand(rolle)), { recursive: true });
    await kontext.storageState({ path: zustand(rolle) });
    await kontext.close();
  }
  await browser.close();
}
