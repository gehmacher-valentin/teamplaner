from django.apps import AppConfig


class NotizenConfig(AppConfig):
    name = "notizen"
    verbose_name = "Notizen"

    def ready(self):
        from . import signale  # noqa: F401 – registriert die Empfänger
