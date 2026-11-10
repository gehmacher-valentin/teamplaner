from django.contrib.auth import views as auth_views
from django.urls import path

from . import einstellungen as einst
from . import views

urlpatterns = [
    path("start/", views.start, name="start"),
    path("anmelden/", views.AnmeldenView.as_view(), name="login"),
    path("anmelden/code/", views.anmelden_code, name="anmelden_code"),
    path("passwort/vergessen/", views.passwort_vergessen, name="passwort_vergessen"),
    path("abmelden/", auth_views.LogoutView.as_view(), name="logout"),
    path("passwort/setzen/<uidb64>/<token>/", views.PasswortSetzenView.as_view(), name="passwort_setzen"),

    # Einstellungsbereich: Persönlich
    path("einstellungen/", einst.start, name="einstellungen"),
    path("einstellungen/profil/", einst.profil, name="einst_profil"),
    path("einstellungen/sicherheit/", views.PasswortAendernView.as_view(), name="einst_sicherheit"),
    path("einstellungen/benachrichtigungen/", einst.benachrichtigungen, name="einst_benachrichtigungen"),
    path("einstellungen/benachrichtigungen/speichern/", einst.benachrichtigung_speichern, name="einst_benachrichtigung"),
    path("einstellungen/darstellung/", einst.darstellung, name="einst_darstellung"),
    path("einstellungen/darstellung/speichern/", einst.darstellung_speichern, name="einst_darstellung_speichern"),
    # Team
    path("einstellungen/personen/", views.personen, name="einst_personen"),
    path("einstellungen/personen/einladen/", views.person_einladen, name="einst_person_einladen"),
    path("einstellungen/personen/platzhalter/", views.platzhalter_neu, name="einst_platzhalter_neu"),
    path("einstellungen/personen/<int:pk>/", views.person_seite, name="einst_person"),
    path("einstellungen/personen/<int:pk>/freigabe/", views.person_freigabe, name="einst_person_freigabe"),
    path("einstellungen/ansichten/", einst.ansichten, name="einst_ansichten"),
    path("einstellungen/ansichten/<str:art>/reihenfolge/", einst.ansichten_sortieren, name="einst_ansichten_sortieren"),
    path("einstellungen/rollen/", einst.rollen, name="einst_rollen"),
    # System
    path("einstellungen/allgemein/", einst.allgemein, name="einst_allgemein"),
    path("einstellungen/listen/", einst.listen, name="einst_listen"),
    path("einstellungen/listen/<str:art>/neu/", einst.liste_neu, name="einst_liste_neu"),
    path("einstellungen/listen/<str:art>/reihenfolge/", einst.liste_sortieren, name="einst_liste_sortieren"),
    path("einstellungen/listen/<str:art>/<int:pk>/", einst.liste_eintrag, name="einst_liste_eintrag"),
    path("einstellungen/listen/<str:art>/<int:pk>/loeschen/", einst.liste_loeschen, name="einst_liste_loeschen"),
    path("einstellungen/kalender/", einst.kalender, name="einst_kalender"),
    path("einstellungen/kalender/zeitraum/", einst.kalender_zeitraum, name="einst_kalender_zeitraum"),
    path("einstellungen/kalender/<int:pk>/", einst.kalender_tag, name="einst_kalender_tag"),
    path("einstellungen/speicherplatz/", views.anhaenge, name="einst_speicherplatz"),
    path("einstellungen/speicherplatz/<int:pk>/loeschen/", views.anhang_entfernen, name="anhang_entfernen"),
    path("einstellungen/ueber/", einst.ueber, name="einst_ueber"),

    # Aktionen zum Konto und zu Personen (nur POST)
    path("konto/zwei-faktor/", views.zwei_faktor_einrichten, name="zwei_faktor_einrichten"),
    path("konto/zwei-faktor/<str:aktion>/", views.zwei_faktor_aendern, name="zwei_faktor_aendern"),
    path("personen/<int:pk>/<str:aktion>/", views.person_aktion, name="person_aktion"),
    path("platzhalter/<int:pk>/umwandeln/", views.platzhalter_umwandeln, name="platzhalter_umwandeln"),
    path("platzhalter/<int:pk>/<str:aktion>/", views.platzhalter_aktion, name="platzhalter_aktion"),

    path("protokoll/", views.protokoll, name="protokoll"),
]
