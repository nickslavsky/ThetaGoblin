from django.contrib import admin
from django.urls import path
from django.views.generic import RedirectView

from screener.views import candidates_view, refresh_candidates

urlpatterns = [
    path("admin/", admin.site.urls),
    path("candidates/", candidates_view, name="candidates"),
    path("candidates/refresh/", refresh_candidates, name="refresh_candidates"),
    path("", RedirectView.as_view(url="/candidates/", permanent=False)),
]
