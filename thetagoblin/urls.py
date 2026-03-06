from django.contrib import admin
from django.urls import path
from django.views.generic import RedirectView

from screener.views import candidates_view, refresh_candidates, suppress_symbol

urlpatterns = [
    path("admin/", admin.site.urls),
    path("candidates/", candidates_view, name="candidates"),
    path("candidates/refresh/", refresh_candidates, name="refresh_candidates"),
    path("candidates/suppress/", suppress_symbol, name="suppress_symbol"),
    path("", RedirectView.as_view(url="/candidates/", permanent=False)),
]
