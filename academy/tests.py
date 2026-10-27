from unittest.mock import patch
from django.db import DatabaseError
from django.test import TestCase
from django.urls import reverse
from .lessons import LESSONS

class LearningTests(TestCase):
    def test_index_contains_every_lesson(self):
        response = self.client.get(reverse("academy:index"))
        for lesson in LESSONS:
            self.assertContains(response, reverse("academy:lesson", args=[lesson["slug"]]))

    def test_every_lesson_renders_nonempty_markdown(self):
        for lesson in LESSONS:
            with self.subTest(lesson=lesson["slug"]):
                response = self.client.get(reverse("academy:lesson", args=[lesson["slug"]]))
                self.assertEqual(response.status_code, 200)
                self.assertGreater(len(response.context["content_html"]), 1000)
                self.assertIn("<h2", response.context["content_html"])

    def test_unknown_lesson_is_404(self):
        self.assertEqual(self.client.get("/learn/unknown/").status_code, 404)

    def test_health_queries_database(self):
        self.assertEqual(self.client.get("/health/").json(), {"status": "ok"})

    def test_health_reports_database_outage(self):
        with patch("ronaldu.views.connection.cursor", side_effect=DatabaseError("private details")):
            with self.assertLogs("ronaldu.views", level="ERROR"):
                response = self.client.get("/health/")
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json(), {"status": "unavailable"})
