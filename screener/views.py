import json
import logging

from django.http import JsonResponse, StreamingHttpResponse
from django.shortcuts import render
from django.template.loader import render_to_string
from django.views.decorators.http import require_POST

from screener.models import FilterConfig, IVRank, Symbol
from screener.services.candidates import get_qualifying_symbols
from screener.services.live_options import stream_live_candidates

logger = logging.getLogger(__name__)


def candidates_view(request):
    """Render the candidates shell page. Data arrives via SSE stream."""
    return render(request, "screener/candidates.html")


def candidates_stream(request):
    """SSE endpoint: streams candidate cards as HTML fragments."""

    def event_stream():
        cfg = {fc.key: fc.typed_value for fc in FilterConfig.objects.all()}
        qualifying_symbols = get_qualifying_symbols()

        iv_ranks = {
            r.symbol_id: r
            for r in IVRank.objects.filter(symbol__in=qualifying_symbols)
        }

        count = 0
        for candidate in stream_live_candidates(qualifying_symbols, cfg, iv_ranks):
            html = render_to_string(
                "screener/_candidate_card.html", {"candidate": candidate}
            )
            sse_data = "\n".join(f"data: {line}" for line in html.split("\n"))
            yield f"event: candidate\n{sse_data}\n\n"
            count += 1

        yield f"event: done\ndata: {count}\n\n"

    response = StreamingHttpResponse(
        event_stream(), content_type="text/event-stream"
    )
    response["Cache-Control"] = "no-cache"
    response["X-Accel-Buffering"] = "no"
    return response


@require_POST
def suppress_symbol(request):
    """Set suppress_until on a Symbol. Called via AJAX from candidates page."""
    try:
        body = json.loads(request.body)
        symbol = Symbol.objects.get(pk=body["symbol_id"])
        symbol.suppress_until = body["suppress_until"]
        symbol.save(update_fields=["suppress_until"])
        return JsonResponse({"status": "ok"})
    except Symbol.DoesNotExist:
        return JsonResponse({"error": "Symbol not found"}, status=404)
