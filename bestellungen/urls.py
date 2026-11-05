from django.urls import path

from . import views

urlpatterns = [
    path("bestellungen/", views.liste, name="bestellungen"),
    path("bestellungen/neu/", views.anlegen, name="bestellung_neu"),
    path("bestellungen/<int:pk>/", views.aendern, name="bestellung"),
    path("bestellungen/<int:pk>/loeschen/", views.loeschen, name="bestellung_loeschen"),
]
