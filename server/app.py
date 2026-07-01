import hashlib
import os
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from functools import wraps
from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory, session


SERVER_DIR = Path(__file__).parent
BASE_DIR = SERVER_DIR.parent
DEFAULT_DB = SERVER_DIR / "data" / "annotations.db"
DEFAULT_SITE_DIR = BASE_DIR / "site"
ALLOWED_COLORS = {"yellow", "green", "blue", "pink"}


def utc_now():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def make_text_hash(selected_text, prefix_text="", suffix_text=""):
    source = f"{prefix_text}\n{selected_text}\n{suffix_text}"
    return hashlib.sha256(source.encode("utf-8")).hexdigest()


def init_db(db_path):
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(path)) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS annotations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                page_path TEXT NOT NULL,
                selected_text TEXT NOT NULL,
                prefix_text TEXT NOT NULL DEFAULT '',
                suffix_text TEXT NOT NULL DEFAULT '',
                text_hash TEXT NOT NULL,
                color TEXT NOT NULL DEFAULT 'yellow',
                note TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_annotations_page_path ON annotations(page_path)"
        )
        conn.commit()


def create_app(test_config=None):
    app = Flask(__name__)
    app.config.update(
        FLASK_SECRET_KEY=os.environ.get("FLASK_SECRET_KEY", "change-me-dev-secret"),
        ANNOTATION_PASSWORD=os.environ.get("ANNOTATION_PASSWORD", "change-me"),
        ANNOTATION_DB=os.environ.get("ANNOTATION_DB", str(DEFAULT_DB)),
        SITE_DIR=os.environ.get("SITE_DIR", str(DEFAULT_SITE_DIR)),
    )
    if test_config:
        app.config.update(test_config)
    app.secret_key = app.config["FLASK_SECRET_KEY"] or app.config["SECRET_KEY"]
    init_db(app.config["ANNOTATION_DB"])

    def get_db():
        conn = sqlite3.connect(app.config["ANNOTATION_DB"])
        conn.row_factory = sqlite3.Row
        return conn

    def annotation_to_dict(row):
        return {
            "id": row["id"],
            "page_path": row["page_path"],
            "selected_text": row["selected_text"],
            "prefix_text": row["prefix_text"],
            "suffix_text": row["suffix_text"],
            "text_hash": row["text_hash"],
            "color": row["color"],
            "note": row["note"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    def require_login(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            if not session.get("authenticated"):
                return jsonify({"error": "authentication_required"}), 401
            return fn(*args, **kwargs)

        return wrapper

    def json_body():
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            return {}
        return data


    @app.get("/")
    def serve_index():
        return send_from_directory(app.config["SITE_DIR"], "index.html")

    @app.get("/<path:filename>")
    def serve_static_site(filename):
        if filename.startswith("api/"):
            return jsonify({"error": "not_found"}), 404
        return send_from_directory(app.config["SITE_DIR"], filename)
    @app.get("/api/me")
    def me():
        return jsonify({"authenticated": bool(session.get("authenticated"))})

    @app.post("/api/login")
    def login():
        data = json_body()
        if data.get("password") != app.config["ANNOTATION_PASSWORD"]:
            return jsonify({"error": "invalid_password"}), 401
        session["authenticated"] = True
        return jsonify({"ok": True})

    @app.post("/api/logout")
    def logout():
        session.clear()
        return jsonify({"ok": True})

    @app.get("/api/annotations")
    @require_login
    def list_annotations():
        page = request.args.get("page", "").strip()
        if not page:
            return jsonify({"error": "page_required"}), 400
        with closing(get_db()) as conn:
            rows = conn.execute(
                """
                SELECT * FROM annotations
                WHERE page_path = ?
                ORDER BY created_at ASC, id ASC
                """,
                (page,),
            ).fetchall()
        return jsonify({"items": [annotation_to_dict(row) for row in rows]})

    @app.post("/api/annotations")
    @require_login
    def create_annotation():
        data = json_body()
        page_path = str(data.get("page_path", "")).strip()
        selected_text = str(data.get("selected_text", "")).strip()
        prefix_text = str(data.get("prefix_text", ""))[:200]
        suffix_text = str(data.get("suffix_text", ""))[:200]
        color = str(data.get("color", "yellow")).strip() or "yellow"
        note = str(data.get("note", ""))

        if not page_path:
            return jsonify({"error": "page_path_required"}), 400
        if not selected_text:
            return jsonify({"error": "selected_text_required"}), 400
        if color not in ALLOWED_COLORS:
            color = "yellow"

        now = utc_now()
        text_hash = make_text_hash(selected_text, prefix_text, suffix_text)
        with closing(get_db()) as conn:
            cur = conn.execute(
                """
                INSERT INTO annotations
                    (page_path, selected_text, prefix_text, suffix_text, text_hash, color, note, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    page_path,
                    selected_text,
                    prefix_text,
                    suffix_text,
                    text_hash,
                    color,
                    note,
                    now,
                    now,
                ),
            )
            conn.commit()
            annotation_id = int(cur.lastrowid)
        return jsonify({"id": annotation_id}), 201

    @app.put("/api/annotations/<int:annotation_id>")
    @require_login
    def update_annotation(annotation_id):
        data = json_body()
        allowed = {}
        if "note" in data:
            allowed["note"] = str(data.get("note", ""))
        if "color" in data:
            color = str(data.get("color", "yellow")).strip() or "yellow"
            allowed["color"] = color if color in ALLOWED_COLORS else "yellow"
        if not allowed:
            return jsonify({"error": "nothing_to_update"}), 400

        allowed["updated_at"] = utc_now()
        assignments = ", ".join(f"{key} = ?" for key in allowed)
        values = list(allowed.values()) + [annotation_id]
        with closing(get_db()) as conn:
            cur = conn.execute(
                f"UPDATE annotations SET {assignments} WHERE id = ?",
                values,
            )
            conn.commit()
            if cur.rowcount == 0:
                return jsonify({"error": "not_found"}), 404
        return jsonify({"ok": True})

    @app.delete("/api/annotations/<int:annotation_id>")
    @require_login
    def delete_annotation(annotation_id):
        with closing(get_db()) as conn:
            cur = conn.execute("DELETE FROM annotations WHERE id = ?", (annotation_id,))
            conn.commit()
            if cur.rowcount == 0:
                return jsonify({"error": "not_found"}), 404
        return jsonify({"ok": True})

    return app


app = create_app()


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000)




