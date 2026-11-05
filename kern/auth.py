from asgiref.sync import sync_to_async
from axes.helpers import get_client_ip_address, get_cool_off
from axes.models import AccessAttempt
from django.conf import settings
from django.contrib.auth.backends import ModelBackend
from django.db.models import Sum
from django.utils import timezone

from .models import Konto


def zu_viele_fehlversuche_von_ip(request):
    """Drosselung je IP-Adresse über alle Konten – gegen das Durchprobieren vieler Konten von einem
    Rechner aus. Die Grenze liegt höher als die Sperre je Konto, weil sich ein
    Firmennetz eine Adresse teilen kann. Gezählt werden die Fehlversuche, die django-axes im
    Sperrzeitraum gespeichert hat; abgewiesene Anfragen zählen nicht mit."""
    grenze = settings.TEAMPLANER_FEHLVERSUCHE_JE_IP
    ip = get_client_ip_address(request)
    if grenze <= 0 or not ip:
        return False
    seit = timezone.now() - get_cool_off(request)
    anzahl = (AccessAttempt.objects.filter(ip_address=ip, attempt_time__gte=seit)
              .aggregate(n=Sum("failures_since_start"))["n"])
    return (anzahl or 0) >= grenze


def axes_benutzername(request, credentials):
    """Schlüssel der Sperre nach Fehlversuchen (django-axes): die E-Mail so, wie die Anmeldung sie
    vergleicht – ohne Leerzeichen und Groß-/Kleinschreibung. Sonst zählten „Admin@…“ und „admin@…“
    getrennt und die Sperre ließe sich durch andere Schreibweisen umgehen."""
    if credentials:
        wert = credentials.get(settings.AXES_USERNAME_FORM_FIELD)
    elif request is not None:
        wert = getattr(request, "data", request.POST).get(settings.AXES_USERNAME_FORM_FIELD)
    else:
        wert = None
    return wert.strip().lower() if isinstance(wert, str) and wert.strip() else None


class KontoBackend(ModelBackend):
    """Anmeldung mit E-Mail (Groß-/Kleinschreibung egal); deaktivierte Konten werden abgewiesen."""

    def get_user(self, user_id):
        try:
            konto = Konto.objects.select_related("person", "person__bereich").get(pk=user_id)
        except Konto.DoesNotExist:
            return None
        return konto if self.user_can_authenticate(konto) else None

    async def aget_user(self, user_id):
        # is_active liest die Person – im Async-Kontext (SSE) daher über einen Thread
        return await sync_to_async(self.get_user)(user_id)

    # Rechte laufen über kern.rechte, nicht über Django-Permissions
    def get_all_permissions(self, user_obj, obj=None):
        return set()

    def has_perm(self, user_obj, perm, obj=None):
        return False
