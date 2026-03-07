from django.contrib.auth.models import User
from django.test import TestCase, Client
from screener.models import FilterConfig, Symbol


class AdminAccessTest(TestCase):

    def setUp(self):
        self.admin_user = User.objects.create_superuser(
            username="admin", email="admin@test.com", password="adminpass123"
        )
        self.client = Client()
        self.client.login(username="admin", password="adminpass123")

    def test_filterconfig_changelist_loads(self):
        resp = self.client.get("/admin/screener/filterconfig/")
        self.assertEqual(resp.status_code, 200)

    def test_filterconfig_shows_description_column(self):
        resp = self.client.get("/admin/screener/filterconfig/")
        # The list_display includes 'description' — verify it's rendered
        self.assertContains(resp, "description")

    def test_filterconfig_shows_seed_descriptions(self):
        resp = self.client.get("/admin/screener/filterconfig/")
        # The seed migration added descriptions — one of them should appear
        self.assertContains(resp, "Minimum market cap")

    def test_symbol_changelist_loads(self):
        resp = self.client.get("/admin/screener/symbol/")
        self.assertEqual(resp.status_code, 200)

    def test_earnings_date_changelist_loads(self):
        resp = self.client.get("/admin/screener/earningsdate/")
        self.assertEqual(resp.status_code, 200)

    def test_iv30_snapshot_changelist_loads(self):
        resp = self.client.get("/admin/screener/iv30snapshot/")
        self.assertEqual(resp.status_code, 200)

    def test_iv_rank_changelist_loads(self):
        resp = self.client.get("/admin/screener/ivrank/")
        self.assertEqual(resp.status_code, 200)

    def test_admin_requires_login(self):
        self.client.logout()
        resp = self.client.get("/admin/screener/filterconfig/")
        # Should redirect to login
        self.assertEqual(resp.status_code, 302)
        self.assertIn("login", resp["Location"])
