"""Главная таблица маршрутов: URL → view. Порядок имеет значение."""
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path
from .views import health

urlpatterns = [
    path("admin/", admin.site.urls),
    path("health/", health, name="health"),
    path("accounts/login/", auth_views.LoginView.as_view(), name="login"),
    path("accounts/logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("learn/", include("academy.urls")),
    path("api/", include("commerce.api_urls")),
    path("", include("commerce.urls")),
    path("", include("main.urls")),
]
if settings.DEBUG:
    # В production пользовательские файлы отдаёт отдельный сервер/storage.
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
