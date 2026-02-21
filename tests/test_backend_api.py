from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from backend.main import app
from backend.report_store import ReportStore


def write_json(path: Path, payload: dict) -> None:
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle)


class BackendApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        reports = root / "reports" / "example_20260101"
        reports.mkdir(parents=True, exist_ok=True)

        page = {
            "url": "https://example.com/",
            "audit_status": "complete",
            "onpage_seo": {"score": 80, "issues": []},
            "schema_analysis": {"score": 20},
            "content_analysis": {"score": 60, "issues": [{"severity": "high", "description": "Issue A"}]},
            "link_analysis": {"score": 50, "issues": []},
            "performance": {"score": 70},
            "readability": {"score": 90, "issues": []},
            "security": {"score": 80, "issues": []},
            "accessibility": {"score": 75, "issues": []},
            "canonical_analysis": {"score": 40},
            "overall_score": 66.8,
            "letter_grade": "D",
        }
        write_json(reports / "page-a.json", page)
        write_json(reports / "_site_summary.json", {"overall_score": 66.8, "overall_grade": "D"})

        import backend.main as backend_main

        backend_main.store = ReportStore(root)
        self.client = TestClient(app)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_sessions_endpoint(self) -> None:
        res = self.client.get("/api/sessions")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["pages_count"], 1)

    def test_pages_endpoint_contains_risk_index(self) -> None:
        res = self.client.get("/api/sessions/example_20260101/pages")
        self.assertEqual(res.status_code, 200)
        payload = res.json()
        self.assertEqual(payload["total"], 1)
        self.assertIn("risk_index", payload["items"][0])

    def test_page_detail_endpoint(self) -> None:
        res = self.client.get("/api/sessions/example_20260101/pages/page-a")
        self.assertEqual(res.status_code, 200)
        payload = res.json()
        self.assertEqual(payload["summary"]["page_id"], "page-a")
        self.assertEqual(payload["raw_data"]["url"], "https://example.com/")

    def test_export_csv(self) -> None:
        res = self.client.get("/api/sessions/example_20260101/exports.csv")
        self.assertEqual(res.status_code, 200)
        self.assertIn("text/csv", res.headers.get("content-type", ""))
        self.assertIn("page_id", res.text)


if __name__ == "__main__":
    unittest.main()

