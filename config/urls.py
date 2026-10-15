from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path

admin.site.site_header = "Los Churros Rellenos · Inventario"
admin.site.site_title = "Inventario"
admin.site.index_title = "Panel del dueño"

urlpatterns = [
    path("admin/", admin.site.urls),
    path("login/", auth_views.LoginView.as_view(), name="login"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("api/", include("inventario.api_urls")),
    path("", include("pwa.urls")),
]
