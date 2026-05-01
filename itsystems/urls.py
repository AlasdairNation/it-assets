from django.urls import path

from itsystems import views

urlpatterns = [
    path("", views.ITSystemsRegister.as_view(), name="it_systems_register"),
]
