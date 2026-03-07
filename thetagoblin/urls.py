from django.contrib import admin
from django.urls import path
from django.views.generic import RedirectView

from screener.views import candidates_stream, candidates_view, suppress_symbol

urlpatterns = [
    path("admin/", admin.site.urls),
    path("candidates/", candidates_view, name="candidates"),
    path("candidates/stream/", candidates_stream, name="candidates_stream"),
    path("candidates/suppress/", suppress_symbol, name="suppress_symbol"),
    path("", RedirectView.as_view(url="/candidates/", permanent=False)),
]
