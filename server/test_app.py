import json
import os
import tempfile
from pathlib import Path
import unittest

from server.app import create_app


class AnnotationApiTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.tmp.name, "annotations.db")
        self.app = create_app(
            {
                "TESTING": True,
                "ANNOTATION_PASSWORD": "secret",
                "FLASK_SECRET_KEY": "test-secret",
                "ANNOTATION_DB": self.db_path,
                "SITE_DIR": os.path.join(self.tmp.name, "site"),
            }
        )
        self.client = self.app.test_client()

    def tearDown(self):
        self.tmp.cleanup()

    def login(self):
        return self.client.post("/api/login", json={"password": "secret"})

    def test_serves_static_index_for_local_development(self):
        site_dir = Path(self.app.config["SITE_DIR"])
        site_dir.mkdir(parents=True, exist_ok=True)
        (site_dir / "index.html").write_text("<h1>Local Wiki</h1>", encoding="utf-8")

        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Local Wiki", response.data)
    def test_me_reports_unauthenticated_before_login(self):
        response = self.client.get("/api/me")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {"authenticated": False})

    def test_annotations_require_login(self):
        response = self.client.get("/api/annotations?page=/index.html")
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.get_json()["error"], "authentication_required")

    def test_login_rejects_wrong_password(self):
        response = self.client.post("/api/login", json={"password": "wrong"})
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.get_json()["error"], "invalid_password")

    def test_login_accepts_configured_password(self):
        response = self.login()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {"ok": True})

        response = self.client.get("/api/me")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {"authenticated": True})

    def test_authenticated_client_can_crud_annotation(self):
        self.login()

        create_response = self.client.post(
            "/api/annotations",
            data=json.dumps(
                {
                    "page_path": "/topics/topic-precision-localization-code.html",
                    "selected_text": "MqttAdapter",
                    "prefix_text": "它用 ",
                    "suffix_text": " 处理飞控状态",
                    "color": "yellow",
                    "note": "MQTT 适配层",
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(create_response.status_code, 201)
        annotation_id = create_response.get_json()["id"]
        self.assertIsInstance(annotation_id, int)

        list_response = self.client.get(
            "/api/annotations?page=/topics/topic-precision-localization-code.html"
        )
        self.assertEqual(list_response.status_code, 200)
        items = list_response.get_json()["items"]
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["id"], annotation_id)
        self.assertEqual(items[0]["selected_text"], "MqttAdapter")
        self.assertEqual(items[0]["note"], "MQTT 适配层")
        self.assertEqual(items[0]["color"], "yellow")
        self.assertIn("text_hash", items[0])

        update_response = self.client.put(
            f"/api/annotations/{annotation_id}",
            json={"note": "更新后的笔记", "color": "green"},
        )
        self.assertEqual(update_response.status_code, 200)
        self.assertEqual(update_response.get_json(), {"ok": True})

        list_response = self.client.get(
            "/api/annotations?page=/topics/topic-precision-localization-code.html"
        )
        item = list_response.get_json()["items"][0]
        self.assertEqual(item["note"], "更新后的笔记")
        self.assertEqual(item["color"], "green")

        delete_response = self.client.delete(f"/api/annotations/{annotation_id}")
        self.assertEqual(delete_response.status_code, 200)
        self.assertEqual(delete_response.get_json(), {"ok": True})

        list_response = self.client.get(
            "/api/annotations?page=/topics/topic-precision-localization-code.html"
        )
        self.assertEqual(list_response.get_json()["items"], [])


if __name__ == "__main__":
    unittest.main()




