from django.apps import AppConfig


class ZusammenarbeitConfig(AppConfig):
    name = "zusammenarbeit"
    verbose_name = "Kommentare und Anhänge"

    def ready(self):
        from . import signale  # noqa: F401 – registriert die Empfänger
