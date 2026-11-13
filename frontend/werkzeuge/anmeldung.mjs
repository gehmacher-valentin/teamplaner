// Anmeldung der Demokonten im Browser, gemeinsam für Bildschirmfotos (bildschirmfotos.mjs) und
// Browser-Tests (e2e/). Admin und Bereichsleitung müssen die Zwei-Faktor-Anmeldung einrichten:
// das geht nur einmal je Konto, also mit frischen Demodaten.
import { createHmac } from "node:crypto";

export const DEMO_PASSWORT = process.env.DEMO_PASSWORT ?? "Teamplaner-Demo-2026";

/** Sechsstelliger Code einer Authenticator-App (TOTP, 30 s) zum Base32-Schlüssel. */
export function einmalcode(geheimnis) {
  const bits = geheimnis.replace(/\s/g, "").toUpperCase().split("")
    .map((z) => "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567".indexOf(z).toString(2).padStart(5, "0")).join("");
  const schluessel = Buffer.from(bits.match(/.{8}/g).map((b) => parseInt(b, 2)));
  const zaehler = Buffer.alloc(8);
  zaehler.writeBigUInt64BE(BigInt(Math.floor(Date.now() / 30000)));
  const hash = createHmac("sha1", schluessel).update(zaehler).digest();
  return String((hash.readUInt32BE(hash[19] & 15) & 0x7fffffff) % 1000000).padStart(6, "0");
}

/** Meldet das Konto auf der Seite an und richtet bei Bedarf die Zwei-Faktor-Anmeldung ein. */
export async function anmelden(seite, basis, email, passwort = DEMO_PASSWORT) {
  await seite.goto(`${basis}/anmelden/`);
  await seite.fill('input[name="username"]', email);
  await seite.fill('input[name="password"]', passwort);
  await Promise.all([seite.waitForURL((url) => !url.pathname.startsWith("/anmelden")), seite.click('button[type="submit"]')]);
  if (seite.url().includes("/zwei-faktor/")) {
    await seite.fill('input[name="code"]', einmalcode(await seite.textContent("code.mono")));
    await seite.fill('input[name="passwort"]', passwort);
    await Promise.all([seite.waitForLoadState("load"), seite.click('form.formular button[type="submit"]')]);
  }
  return seite;
}
