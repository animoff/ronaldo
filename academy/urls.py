from django.urls import path
from . import views
app_name = "academy"
urlpatterns = [
    path("", views.index, name="index"),
    path("<slug:slug>/", views.lesson, name="lesson"),
]
