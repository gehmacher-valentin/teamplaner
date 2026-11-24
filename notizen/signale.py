"""Dateien eines Notiz-Anhangs mit dem Datensatz löschen (registriert in NotizenConfig.ready)."""

from django.db.models.signals import post_delete

from zusammenarbeit.anhaenge import dateien_entfernen

from .models import NotizAnhang

post_delete.connect(dateien_entfernen, sender=NotizAnhang, dispatch_uid="notiz_anhang_dateien_entfernen")
