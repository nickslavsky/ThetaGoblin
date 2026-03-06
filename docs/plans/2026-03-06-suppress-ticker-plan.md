# Suppress Ticker Until Expiry — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** One-click suppression of a ticker from the candidates view until a chosen option expiry date.

**Architecture:** Add a nullable `suppress_until` DateField to Symbol, filter it in the candidates pipeline, expose a POST endpoint, and wire expiry cells in the template to call it via fetch() and remove the ticker card from the DOM.

**Tech Stack:** Django 5.x, PostgreSQL, vanilla JS (fetch API), Django CSRF token.

---

### Task 1: Add `suppress_until` field to Symbol model + migration

**Files:**
- Modify: `screener/models.py:4-19` (Symbol model)
- Create: new migration via `makemigrations`

**Step 1: Add the field**

In `screener/models.py`, add after line 12 (`ten_day_avg_trading_volume`):

```python
    suppress_until = models.DateField(
        null=True, blank=True,
        help_text="Hide from candidates until this date (exclusive — reappears day after)",
    )
```

**Step 2: Generate migration**

Run: `docker compose exec web python manage.py makemigrations screener`
Expected: `0010_symbol_suppress_until.py` (or next number) created.

**Step 3: Apply migration**

Run: `docker compose exec web python manage.py migrate`
Expected: `OK`

**Step 4: Commit**

```bash
git add screener/models.py screener/migrations/0010_*.py
git commit -m "feat: add suppress_until field to Symbol model"
```

---

### Task 2: Expose `suppress_until` in Django admin

**Files:**
- Modify: `screener/admin.py:17-25` (SymbolAdmin)

**Step 1: Add to list_display and make editable**

In `screener/admin.py`, update `SymbolAdmin`:

```python
@admin.register(Symbol)
class SymbolAdmin(admin.ModelAdmin):
    list_display = [
        "ticker", "name", "exchange_mic", "market_cap",
        "operating_margin", "ten_day_avg_trading_volume",
        "suppress_until", "fundamentals_updated_at",
    ]
    list_filter = ["exchange_mic"]
    search_fields = ["ticker", "name"]
    readonly_fields = ["fundamentals_updated_at"]
    ordering = ["ticker"]
```

Note: `suppress_until` is NOT in `readonly_fields`, so it's editable in the detail view. It's in `list_display` for visibility but NOT in `list_editable` (editing dates inline in lists is awkward — use the detail form).

**Step 2: Verify in admin**

Run: `docker compose exec web python manage.py runserver 0.0.0.0:8000`
Visit: `http://localhost:8000/admin/screener/symbol/` — confirm `suppress_until` column appears.

**Step 3: Commit**

```bash
git add screener/admin.py
git commit -m "feat: expose suppress_until in Symbol admin"
```

---

### Task 3: Filter suppressed symbols in candidates pipeline (TDD)

**Files:**
- Modify: `screener/services/candidates.py:9-51`
- Modify: `screener/tests/test_candidates.py`

**Step 1: Write failing tests**

Add to `screener/tests/test_candidates.py`. The existing `IVRankFilterTest.setUp` creates a qualifying symbol with all FilterConfig seeds. Follow the same pattern:

```python
class SuppressUntilFilterTest(TestCase):
    """Tests for suppress_until filtering in get_qualifying_symbols()."""

    def setUp(self):
        self.sym = Symbol.objects.create(
            ticker="MSFT", exchange_mic="XNAS", name="Microsoft Corp",
            market_cap=3_000_000_000_000,
            operating_margin=0.40,
            cash_flow_per_share_annual=10.0,
            long_term_debt_to_equity_annual=0.8,
            ten_day_avg_trading_volume=5_000_000,
        )

    def test_suppressed_today_excluded(self):
        """Symbol with suppress_until == today should NOT appear."""
        self.sym.suppress_until = date.today()
        self.sym.save()
        result = get_qualifying_symbols()
        self.assertNotIn(self.sym, result)

    def test_suppressed_future_excluded(self):
        """Symbol with suppress_until in the future should NOT appear."""
        self.sym.suppress_until = date.today() + timedelta(days=30)
        self.sym.save()
        result = get_qualifying_symbols()
        self.assertNotIn(self.sym, result)

    def test_suppressed_yesterday_included(self):
        """Symbol with suppress_until == yesterday should appear (strict inequality)."""
        self.sym.suppress_until = date.today() - timedelta(days=1)
        self.sym.save()
        result = get_qualifying_symbols()
        self.assertIn(self.sym, result)

    def test_null_suppress_until_included(self):
        """Symbol with no suppress_until should appear."""
        self.assertIsNone(self.sym.suppress_until)
        result = get_qualifying_symbols()
        self.assertIn(self.sym, result)
```

Add `timedelta` to the existing `from datetime import date` import at the top of the file.

**Step 2: Run tests to verify they fail**

Run: `docker compose exec web python manage.py test screener.tests.test_candidates.SuppressUntilFilterTest -v2`
Expected: 2 failures (`test_suppressed_today_excluded`, `test_suppressed_future_excluded`) — the filter doesn't exist yet.

**Step 3: Implement the filter**

In `screener/services/candidates.py`, add the suppress filter after the fundamentals queryset (line 24) and before the earnings exclusion (line 26):

```python
    # Suppress filter: hide symbols with suppress_until >= today
    today = date.today()
    symbols = symbols.exclude(suppress_until__gte=today)
```

Note: `today` is already defined on line 26 for earnings. Move the `today = date.today()` line up before the suppress filter, and reuse it for earnings. The final order becomes:

```python
    symbols = Symbol.objects.filter(
        market_cap__isnull=False,
        market_cap__gte=cfg["market_cap_min"],
        operating_margin__gt=cfg["operating_margin_min"],
        cash_flow_per_share_annual__gt=cfg["free_cash_flow_min"],
        long_term_debt_to_equity_annual__lt=cfg["debt_to_equity_max"],
        ten_day_avg_trading_volume__gte=min_avg_volume,
    )

    today = date.today()

    # Suppress filter: hide symbols with active suppress_until
    symbols = symbols.exclude(suppress_until__gte=today)

    # Earnings exclusion
    exclusion_cutoff = today + timedelta(days=cfg["earnings_exclusion_days"])
    ...
```

The `__gte` lookup means: exclude where `suppress_until >= today`. This lets symbols through when `suppress_until < today` (yesterday or earlier) or `suppress_until IS NULL` (Django excludes NULLs from `__gte` comparisons automatically).

**Step 4: Run tests to verify they pass**

Run: `docker compose exec web python manage.py test screener.tests.test_candidates -v2`
Expected: All 9 tests pass (5 existing + 4 new).

**Step 5: Commit**

```bash
git add screener/services/candidates.py screener/tests/test_candidates.py
git commit -m "feat: filter suppressed symbols in candidates pipeline"
```

---

### Task 4: Add suppress endpoint (TDD)

**Files:**
- Modify: `screener/views.py`
- Modify: `thetagoblin/urls.py`
- Modify: `screener/tests/test_views.py`

**Step 1: Write failing tests**

Add to `screener/tests/test_views.py`:

```python
import json

class SuppressViewTest(TestCase):

    def setUp(self):
        self.client = Client()
        self.aapl = Symbol.objects.create(
            ticker="AAPL", exchange_mic="XNAS", name="Apple Inc",
            market_cap=3_000_000_000_000,
            operating_margin=0.30,
            cash_flow_per_share_annual=7.5,
            long_term_debt_to_equity_annual=1.2,
            ten_day_avg_trading_volume=5_000_000,
        )

    def test_suppress_sets_date(self):
        resp = self.client.post(
            "/candidates/suppress/",
            data=json.dumps({"symbol_id": self.aapl.pk, "suppress_until": "2026-04-18"}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        self.aapl.refresh_from_db()
        self.assertEqual(self.aapl.suppress_until, date(2026, 4, 18))

    def test_suppress_returns_json(self):
        resp = self.client.post(
            "/candidates/suppress/",
            data=json.dumps({"symbol_id": self.aapl.pk, "suppress_until": "2026-04-18"}),
            content_type="application/json",
        )
        self.assertEqual(resp["Content-Type"], "application/json")
        body = resp.json()
        self.assertEqual(body["status"], "ok")

    def test_suppress_rejects_get(self):
        resp = self.client.get("/candidates/suppress/")
        self.assertEqual(resp.status_code, 405)

    def test_suppress_missing_symbol_returns_404(self):
        resp = self.client.post(
            "/candidates/suppress/",
            data=json.dumps({"symbol_id": 99999, "suppress_until": "2026-04-18"}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 404)
```

Add `json` to imports and `date` to the `from datetime import` line at the top of the file.

**Step 2: Run tests to verify they fail**

Run: `docker compose exec web python manage.py test screener.tests.test_views.SuppressViewTest -v2`
Expected: 404 errors (URL doesn't exist yet).

**Step 3: Implement the view**

Add to `screener/views.py`:

```python
import json

from django.http import JsonResponse
from django.views.decorators.http import require_POST

from screener.models import FilterConfig, IVRank, OptionsSnapshot, Symbol


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
```

Update the existing imports at the top — add `json`, `JsonResponse`, `require_POST`, and `Symbol` to the appropriate import lines.

**Step 4: Add URL**

In `thetagoblin/urls.py`, add the import and URL:

```python
from screener.views import candidates_view, refresh_candidates, suppress_symbol

urlpatterns = [
    path("admin/", admin.site.urls),
    path("candidates/", candidates_view, name="candidates"),
    path("candidates/refresh/", refresh_candidates, name="refresh_candidates"),
    path("candidates/suppress/", suppress_symbol, name="suppress_symbol"),
    path("", RedirectView.as_view(url="/candidates/", permanent=False)),
]
```

**Step 5: Run tests to verify they pass**

Run: `docker compose exec web python manage.py test screener.tests.test_views.SuppressViewTest -v2`
Expected: All 4 pass.

**Step 6: Run full test suite**

Run: `docker compose exec web python manage.py test screener -v2`
Expected: All tests pass.

**Step 7: Commit**

```bash
git add screener/views.py thetagoblin/urls.py screener/tests/test_views.py
git commit -m "feat: add POST /candidates/suppress/ endpoint"
```

---

### Task 5: Wire up frontend — clickable expiry cells with AJAX

**Files:**
- Modify: `screener/templates/screener/candidates.html:59-69` (table body)
- Modify: `screener/templates/screener/base.html` (add CSS for clickable cells)

**Step 1: Add data attributes to candidate cards and expiry cells**

In `screener/templates/screener/candidates.html`, update the candidate card div (line 27) to include the symbol ID:

```html
    <div class="candidate-card" data-symbol-id="{{ candidate.symbol.pk }}">
```

Update the expiry `<td>` (line 61) to be clickable:

```html
                        <td class="expiry-cell" data-expiry="{{ opt.expiry|date:'Y-m-d' }}">{{ opt.expiry }}</td>
```

**Step 2: Add CSS for clickable expiry cells**

In `screener/templates/screener/base.html`, add to the `<style>` block:

```css
        .expiry-cell { cursor: pointer; user-select: none; border-radius: 4px; transition: background-color 0.15s; }
        .expiry-cell:hover { background-color: var(--pico-primary-background); color: var(--pico-primary-inverse); }
```

**Step 3: Add JavaScript to candidates.html**

Add a `{% block scripts %}` at the end of `candidates.html` (before `{% endblock %}`), or simply add a `<script>` tag at the bottom of the `{% block content %}`:

```html
<script>
document.querySelectorAll('.expiry-cell').forEach(cell => {
    cell.addEventListener('click', function() {
        const card = this.closest('.candidate-card');
        const symbolId = card.dataset.symbolId;
        const suppressUntil = this.dataset.expiry;

        fetch('{% url "suppress_symbol" %}', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': '{{ csrf_token }}',
            },
            body: JSON.stringify({
                symbol_id: parseInt(symbolId),
                suppress_until: suppressUntil,
            }),
        })
        .then(resp => {
            if (resp.ok) {
                card.remove();
                // Update candidate count in header
                const remaining = document.querySelectorAll('.candidate-card').length;
                const countEl = document.querySelector('.header-bar small');
                if (countEl) {
                    const suffix = remaining === 1 ? '' : 's';
                    countEl.textContent = `CSP Candidates — ${remaining} ticker${suffix}`;
                }
            }
        });
    });
});
</script>
```

**Step 4: Manual verification**

Run: `docker compose exec web python manage.py runserver 0.0.0.0:8000`
Visit: `http://localhost:8000/candidates/`
- Hover over an expiry date cell — should highlight with primary color
- Click it — the entire ticker card should disappear
- Refresh page — the ticker should still be gone (filtered by pipeline)
- Check Django admin — the symbol should have `suppress_until` set to the clicked expiry date

**Step 5: Commit**

```bash
git add screener/templates/screener/candidates.html screener/templates/screener/base.html
git commit -m "feat: clickable expiry cells to suppress ticker via AJAX"
```

---

### Task 6: Run full test suite + manual smoke test

**Step 1: Run all tests**

Run: `docker compose exec web python manage.py test screener -v2`
Expected: All tests pass (existing + new suppress tests).

**Step 2: Verify candidates_view still works with suppressed symbol**

Add a `test_suppressed_symbol_hidden_from_view` to `screener/tests/test_views.py` inside `CandidatesViewTest`:

```python
    def test_suppressed_symbol_hidden_from_view(self):
        """Symbol with suppress_until >= today should not appear in candidates."""
        self.aapl.suppress_until = date.today() + timedelta(days=30)
        self.aapl.save()
        resp = self.client.get("/candidates/")
        self.assertNotContains(resp, "AAPL")
```

**Step 3: Run full suite again**

Run: `docker compose exec web python manage.py test screener -v2`
Expected: All pass.

**Step 4: Final commit**

```bash
git add screener/tests/test_views.py
git commit -m "test: add integration test for suppressed symbol in candidates view"
```
