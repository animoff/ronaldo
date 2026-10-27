"""Имена маршрутов позволяют менять URL без поиска строк по всему проекту."""
from django.urls import path
from . import views

app_name = "main"
urlpatterns = [
    path("", views.home, name="home"),
    path("catalog/", views.product_list, name="product_list"),
    # <slug:slug> принимает только ASCII; <str:slug> поддерживает русские адреса.
    path("catalog/<str:slug>/", views.product_detail, name="product_detail"),
]
