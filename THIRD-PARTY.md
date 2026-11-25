# Fremdwerke

Teamplaner steht unter der GNU AGPL-3.0 oder später. Enthalten oder eingebunden sind:

| Werk | Verwendung | Lizenz |
| --- | --- | --- |
| [Fluent Emoji](https://github.com/microsoft/fluentui-emoji) (Microsoft) | Grafiken der Feieranimation, `frontend/src/lib/feiern/` | MIT, siehe `LIZENZ.txt` dort |
| „Unicorn Rainbow“ von Praveen Singh ([LottieFiles](https://lottiefiles.com/)) | Einhorn der Feieranimation, `frontend/src/lib/feiern/einhorn.json` (zugeschnitten) | Lottie Simple License |
| [lottie-web](https://github.com/airbnb/lottie-web) (Airbnb) | Abspielen der Einhorn-Animation | MIT |
| [IBM Plex](https://github.com/IBM/plex) | Schriften Sans und Mono | SIL Open Font License 1.1 |
| [pi-heif](https://github.com/bigcat88/pillow_heif) mit libheif | HEIC-Fotos lesen | LGPL-3.0 und BSD-3-Clause |
| [pypdfium2](https://github.com/pypdfium2-team/pypdfium2) mit [PDFium](https://pdfium.googlesource.com/pdfium/) | Vorschau der ersten Seite von PDF-Anhängen | Apache-2.0 und BSD-3-Clause; mitgelieferte Bibliotheken (u. a. FreeType, libjpeg-turbo, OpenJPEG, Little CMS, ICU, zlib) unter ihren freien Lizenzen, siehe `BUILD_LICENSES` im Paket |

Die übrigen Abhängigkeiten stehen in `requirements.txt` und `frontend/package-lock.json`, mit den Lizenzen
ihrer Projekte (MIT, BSD, Apache-2.0 und vergleichbare).
