from django.apps import AppConfig


class KernConfig(AppConfig):
    name = "kern"
    verbose_name = "Personen und Konten"

    def ready(self):
        from . import signale  # noqa: F401 – registriert die Empfänger
