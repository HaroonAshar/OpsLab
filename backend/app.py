
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os
from urllib.parse import urlparse

import psycopg


def get_connection():
    return psycopg.connect(
        host=os.environ["PGHOST"],
        port=os.environ["PGPORT"],
        dbname=os.environ["PGDATABASE"],
        user=os.environ["PGUSER"],
        password=os.environ["PGPASSWORD"],
        connect_timeout=5,
    )


class APIHandler(BaseHTTPRequestHandler):
    def send_json(self, status, data):
        body = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def read_json(self):
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0 or length > 100_000:
                raise ValueError("Request body size is invalid")

            data = json.loads(self.rfile.read(length))
            if not isinstance(data, dict):
                raise ValueError("JSON body must be an object")

            return data
        except (ValueError, json.JSONDecodeError):
            raise ValueError("Invalid JSON request body")

    def do_GET(self):
        path = urlparse(self.path).path

        if path == "/":
            return self.send_json(200, {"message": "Welcome to OpsLab API"})

        if path == "/health":
            return self.send_json(
                200, {"status": "healthy", "service": "opslab-backend"}
            )

        if path == "/tasks":
            try:
                with get_connection() as conn:
                    rows = conn.execute(
                        """
                        SELECT id, title, completed, created_at
                        FROM tasks ORDER BY id
                        """
                    ).fetchall()

                return self.send_json(200, [
                    {
                        "id": row[0],
                        "title": row[1],
                        "completed": row[2],
                        "created_at": row[3].isoformat(),
                    }
                    for row in rows
                ])
            except Exception:
                self.log_error("Database error while listing tasks")
                return self.send_json(500, {"error": "Database error"})

        if path.startswith("/tasks/"):
            try:
                task_id = int(path.removeprefix("/tasks/"))
                if task_id <= 0:
                    raise ValueError
            except ValueError:
                return self.send_json(400, {"error": "Invalid task ID"})

            try:
                with get_connection() as conn:
                    row = conn.execute(
                        """
                        SELECT id, title, completed, created_at
                        FROM tasks WHERE id = %s
                        """,
                        (task_id,),
                    ).fetchone()

                if row is None:
                    return self.send_json(404, {"error": "Task not found"})

                return self.send_json(200, {
                    "id": row[0],
                    "title": row[1],
                    "completed": row[2],
                    "created_at": row[3].isoformat(),
                })
            except Exception:
                self.log_error("Database error while retrieving task")
                return self.send_json(500, {"error": "Database error"})

        return self.send_json(404, {"error": "Not found"})

    def do_POST(self):
        if urlparse(self.path).path != "/tasks":
            return self.send_json(404, {"error": "Not found"})

        try:
            data = self.read_json()
        except ValueError as exc:
            return self.send_json(400, {"error": str(exc)})

        title = data.get("title")
        if not isinstance(title, str) or not title.strip():
            return self.send_json(400, {"error": "title must be a non-empty string"})

        if len(title.strip()) > 255:
            return self.send_json(400, {"error": "title must be at most 255 characters"})

        try:
            with get_connection() as conn:
                row = conn.execute(
                    """
                    INSERT INTO tasks (title)
                    VALUES (%s)
                    RETURNING id, title, completed, created_at
                    """,
                    (title.strip(),),
                ).fetchone()

            return self.send_json(201, {
                "id": row[0],
                "title": row[1],
                "completed": row[2],
                "created_at": row[3].isoformat(),
            })
        except Exception:
            self.log_error("Database error while creating task")
            return self.send_json(500, {"error": "Database error"})

    def do_PATCH(self):
        if not urlparse(self.path).path.startswith("/tasks/"):
            return self.send_json(404, {"error": "Not found"})

        try:
            task_id = int(urlparse(self.path).path.removeprefix("/tasks/"))
            if task_id <= 0:
                raise ValueError
            data = self.read_json()
        except ValueError as exc:
            return self.send_json(400, {"error": str(exc)})

        if not data or set(data) - {"title", "completed"}:
            return self.send_json(
                400, {"error": "Provide title and/or completed only"}
            )

        if "title" in data and (
            not isinstance(data["title"], str)
            or not data["title"].strip()
            or len(data["title"].strip()) > 255
        ):
            return self.send_json(400, {"error": "Invalid title"})

        if "completed" in data and not isinstance(data["completed"], bool):
            return self.send_json(400, {"error": "completed must be a boolean"})

        try:
            with get_connection() as conn:
                current = conn.execute(
                    "SELECT id, title, completed, created_at FROM tasks WHERE id = %s",
                    (task_id,),
                ).fetchone()

                if current is None:
                    return self.send_json(404, {"error": "Task not found"})

                title = data.get("title", current[1])
                if isinstance(title, str):
                    title = title.strip()
                completed = data.get("completed", current[2])

                row = conn.execute(
                    """
                    UPDATE tasks SET title = %s, completed = %s
                    WHERE id = %s
                    RETURNING id, title, completed, created_at
                    """,
                    (title, completed, task_id),
                ).fetchone()

            return self.send_json(200, {
                "id": row[0],
                "title": row[1],
                "completed": row[2],
                "created_at": row[3].isoformat(),
            })
        except Exception:
            self.log_error("Database error while updating task")
            return self.send_json(500, {"error": "Database error"})

    def do_DELETE(self):
        path = urlparse(self.path).path
        if not path.startswith("/tasks/"):
            return self.send_json(404, {"error": "Not found"})

        try:
            task_id = int(path.removeprefix("/tasks/"))
            if task_id <= 0:
                raise ValueError
        except ValueError:
            return self.send_json(400, {"error": "Invalid task ID"})

        try:
            with get_connection() as conn:
                row = conn.execute(
                    "DELETE FROM tasks WHERE id = %s RETURNING id",
                    (task_id,),
                ).fetchone()

            if row is None:
                return self.send_json(404, {"error": "Task not found"})

            return self.send_json(200, {"deleted": True, "id": row[0]})
        except Exception:
            self.log_error("Database error while deleting task")
            return self.send_json(500, {"error": "Database error"})

    def log_error(self, message):
        # Avoid logging credentials or other sensitive connection details.
        print(message, flush=True)


HOST = os.getenv("HOST", "127.0.0.1")
PORT = int(os.getenv("PORT", "8000"))

server = HTTPServer((HOST, PORT), APIHandler)
print(f"OpsLab API running on {HOST}:{PORT}", flush=True)
server.serve_forever()
