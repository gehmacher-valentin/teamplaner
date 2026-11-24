"""Dateien eines Anhangs mit dem Datensatz löschen (registriert in ZusammenarbeitConfig.ready)."""

from django.db.models.signals import post_delete

from .anhaenge import dateien_entfernen
from .models import Anhang

post_delete.connect(dateien_entfernen, sender=Anhang, dispatch_uid="anhang_dateien_entfernen")
