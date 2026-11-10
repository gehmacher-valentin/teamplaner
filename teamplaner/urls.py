from django.urls import include, path

urlpatterns = [
    path("i18n/", include("django.conf.urls.i18n")),
    # kern zuerst: personen/<pk>/foto/ muss vor personen/<pk>/<aktion>/ aus verwaltung greifen
    path("", include("kern.urls")),
    path("", include("verwaltung.urls")),
    path("", include("planung.urls")),
    path("", include("projekte.urls")),
    path("", include("zusammenarbeit.urls")),
    path("", include("gantt.urls")),
    path("", include("notizen.urls")),
    path("", include("bestellungen.urls")),
]
