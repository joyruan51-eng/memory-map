#!/usr/bin/env python3
import argparse
import base64
import binascii
import hashlib
import hmac
import json
import mimetypes
import os
import re
import secrets
import shutil
import sqlite3
import time
from http import cookies
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import quote, unquote, urlparse


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = Path(os.environ.get("MEMORY_MAP_DATA_DIR", BASE_DIR / "data")).resolve()
UPLOADS_DIR = DATA_DIR / "uploads"
DB_PATH = Path(os.environ.get("MEMORY_MAP_DB_PATH", DATA_DIR / "memory-map.sqlite3")).resolve()
SESSION_COOKIE = "memory_session"
SESSION_SECONDS = 60 * 60 * 24 * 7
PASSWORD_ROUNDS = 180_000
COLORS = {"coral", "teal", "sage", "ink"}

SAMPLE_MEMORIES = [
    {
        "id": "sea-qingdao",
        "title": "第一次独自看海",
        "date": "2019.08",
        "place": "青岛 小麦岛",
        "lat": 36.0529,
        "lng": 120.4308,
        "color": "coral",
        "tags": ["海边", "独处", "夏天"],
        "story": "那天傍晚海风很大，手机快没电，我在礁石边坐到天黑。原来一个人也可以把快乐装得很满。",
    },
    {
        "id": "lamp-shanghai",
        "title": "雨后的路灯",
        "date": "2021.11",
        "place": "上海 衡山路",
        "lat": 31.2048,
        "lng": 121.4411,
        "color": "teal",
        "tags": ["夜路", "朋友", "散步"],
        "story": "雨停以后，树叶上的水一滴一滴掉下来。我们没有赶地铁，慢慢走完了那条街。",
    },
    {
        "id": "home-tree",
        "title": "老家门口的槐树",
        "date": "2016.04",
        "place": "河南 郑州",
        "lat": 34.7466,
        "lng": 113.6254,
        "color": "sage",
        "tags": ["老家", "春天", "家人"],
        "story": "槐花开的时候，整个巷子都是甜味。后来很多东西变了，只有这棵树一直像一个旧坐标。",
    },
    {
        "id": "library-hangzhou",
        "title": "通宵前的图书馆",
        "date": "2018.12",
        "place": "杭州 西湖区",
        "lat": 30.2592,
        "lng": 120.1303,
        "color": "ink",
        "tags": ["考试", "咖啡", "青春"],
        "story": "玻璃窗上映着成排的台灯，我把最后一页笔记合上，突然觉得那一年终于快要过去了。",
    },
    {
        "id": "station-chengdu",
        "title": "清晨的车站",
        "date": "2023.03",
        "place": "成都 东站",
        "lat": 30.6298,
        "lng": 104.1417,
        "color": "coral",
        "tags": ["出发", "清晨", "行李"],
        "story": "天还没亮，候车厅已经有很多人。热豆浆握在手里，我第一次认真期待一段新的生活。",
    },
    {
        "id": "bridge-beijing",
        "title": "冬天桥上的电话",
        "date": "2024.01",
        "place": "北京 亮马河",
        "lat": 39.9473,
        "lng": 116.4708,
        "color": "teal",
        "tags": ["冬天", "电话", "河边"],
        "story": "河面结了一层薄冰。那通电话很短，但我记得自己挂断后站了很久，直到手指冻麻。",
    },
]


def utc_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def allowed_origins() -> set[str]:
    raw = os.environ.get("MEMORY_MAP_ALLOWED_ORIGINS", "")
    return {origin.strip().rstrip("/") for origin in raw.split(",") if origin.strip()}


def cookie_samesite() -> str:
    value = os.environ.get("MEMORY_MAP_COOKIE_SAMESITE", "Lax").strip()
    return value if value in {"Lax", "Strict", "None"} else "Lax"


def env_flag(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


def db() -> sqlite3.Connection:
    connection = sqlite3.connect(DB_PATH, timeout=30)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def init_db() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with db() as connection:
        connection.execute("PRAGMA journal_mode = WAL")
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              username TEXT NOT NULL UNIQUE,
              password_hash TEXT NOT NULL,
              salt TEXT NOT NULL,
              created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS sessions (
              token TEXT PRIMARY KEY,
              user_id INTEGER NOT NULL,
              expires_at INTEGER NOT NULL,
              created_at TEXT NOT NULL,
              FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS memories (
              user_id INTEGER NOT NULL,
              id TEXT NOT NULL,
              title TEXT NOT NULL,
              date TEXT NOT NULL,
              place TEXT NOT NULL,
              lat REAL NOT NULL,
              lng REAL NOT NULL,
              color TEXT NOT NULL,
              tags TEXT NOT NULL,
              story TEXT NOT NULL,
              photos TEXT NOT NULL DEFAULT '[]',
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL,
              PRIMARY KEY(user_id, id),
              FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_memories_user_updated
              ON memories(user_id, updated_at DESC);
            CREATE INDEX IF NOT EXISTS idx_sessions_user
              ON sessions(user_id);
            """
        )
        columns = {row["name"] for row in connection.execute("PRAGMA table_info(memories)")}
        if "photos" not in columns:
            connection.execute("ALTER TABLE memories ADD COLUMN photos TEXT NOT NULL DEFAULT '[]'")


def hash_password(password: str, salt_hex: str) -> str:
    return hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        bytes.fromhex(salt_hex),
        PASSWORD_ROUNDS,
    ).hex()


def create_password_hash(password: str) -> tuple[str, str]:
    salt_hex = secrets.token_hex(16)
    return salt_hex, hash_password(password, salt_hex)


def check_password(password: str, salt_hex: str, expected_hash: str) -> bool:
    return hmac.compare_digest(hash_password(password, salt_hex), expected_hash)


def make_session(connection: sqlite3.Connection, user_id: int) -> str:
    token = secrets.token_urlsafe(32)
    expires_at = int(time.time()) + SESSION_SECONDS
    connection.execute("DELETE FROM sessions WHERE expires_at <= ?", (int(time.time()),))
    connection.execute(
        "INSERT INTO sessions(token, user_id, expires_at, created_at) VALUES (?, ?, ?, ?)",
        (token, user_id, expires_at, utc_now()),
    )
    return token


def seed_memories(connection: sqlite3.Connection, user_id: int) -> None:
    now = utc_now()
    connection.executemany(
        """
        INSERT INTO memories(user_id, id, title, date, place, lat, lng, color, tags, story, photos, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                user_id,
                memory["id"],
                memory["title"],
                memory["date"],
                memory["place"],
                memory["lat"],
                memory["lng"],
                memory["color"],
                json.dumps(memory["tags"], ensure_ascii=False),
                memory["story"],
                "[]",
                now,
                now,
            )
            for memory in SAMPLE_MEMORIES
        ],
    )


def row_to_memory(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "title": row["title"],
        "date": row["date"],
        "place": row["place"],
        "lat": row["lat"],
        "lng": row["lng"],
        "color": row["color"],
        "tags": json.loads(row["tags"]),
        "story": row["story"],
        "photos": json.loads(row["photos"] or "[]"),
    }


def clean_id(value: str) -> str:
    value = re.sub(r"[^\w\u4e00-\u9fa5.-]+", "-", value.strip(), flags=re.UNICODE)
    value = re.sub(r"-+", "-", value).strip("-")
    return value[:80] or f"memory-{secrets.token_hex(5)}"


def validate_memory(payload: dict, memory_id: str | None = None) -> dict:
    title = str(payload.get("title", "")).strip()
    date = str(payload.get("date", "")).strip()
    place = str(payload.get("place", "")).strip()
    story = str(payload.get("story", "")).strip()
    color = str(payload.get("color", "coral")).strip()

    if not (1 <= len(title) <= 32):
        raise ValueError("标题需要 1-32 个字符")
    if not (1 <= len(date) <= 24):
        raise ValueError("日期不能为空")
    if not (1 <= len(place) <= 64):
        raise ValueError("地点不能为空")
    if not (1 <= len(story) <= 240):
        raise ValueError("片段需要 1-240 个字符")
    if color not in COLORS:
        raise ValueError("颜色不支持")

    try:
      lat = float(payload.get("lat"))
      lng = float(payload.get("lng"))
    except (TypeError, ValueError) as exc:
        raise ValueError("坐标需要是数字") from exc

    if not (-90 <= lat <= 90 and -180 <= lng <= 180):
        raise ValueError("坐标范围不正确")

    raw_tags = payload.get("tags", [])
    if isinstance(raw_tags, str):
        raw_tags = re.split(r"[,，]", raw_tags)
    tags = [str(tag).strip()[:16] for tag in raw_tags if str(tag).strip()]
    tags = tags[:12]

    raw_photos = payload.get("photos", [])
    if not isinstance(raw_photos, list):
        raw_photos = []
    photos = [
        str(photo)
        for photo in raw_photos
        if isinstance(photo, str) and photo.startswith("/api/photos/")
    ][:12]

    return {
        "id": clean_id(memory_id or str(payload.get("id", ""))),
        "title": title,
        "date": date,
        "place": place,
        "lat": lat,
        "lng": lng,
        "color": color,
        "tags": tags,
        "story": story,
        "photos": photos,
    }


def save_uploaded_photos(user_id: int, memory_id: str, uploads: list, existing: list[str]) -> list[str]:
    photos = list(existing or [])[:12]
    if not isinstance(uploads, list):
        return photos

    target_dir = UPLOADS_DIR / str(user_id) / clean_id(memory_id)
    target_dir.mkdir(parents=True, exist_ok=True)

    for upload in uploads[:8]:
        if len(photos) >= 12 or not isinstance(upload, dict):
            break

        data_url = str(upload.get("dataUrl", ""))
        match = re.fullmatch(r"data:(image/(png|jpeg|jpg|webp|gif));base64,(.+)", data_url, flags=re.IGNORECASE | re.DOTALL)
        if not match:
            continue

        mime_type = match.group(1).lower().replace("image/jpg", "image/jpeg")
        extension = {
            "image/png": "png",
            "image/jpeg": "jpg",
            "image/webp": "webp",
            "image/gif": "gif",
        }.get(mime_type)
        if not extension:
            continue

        try:
            image_bytes = base64.b64decode(match.group(3), validate=True)
        except (binascii.Error, ValueError):
            continue

        if not image_bytes or len(image_bytes) > 5 * 1024 * 1024:
            continue

        filename = f"{int(time.time() * 1000)}-{secrets.token_hex(4)}.{extension}"
        target = target_dir / filename
        target.write_bytes(image_bytes)
        photos.append(
            f"/api/photos/{user_id}/{quote(clean_id(memory_id))}/{quote(filename)}"
        )

    return photos


def remove_uploads_for_memory(user_id: int, memory_id: str) -> None:
    target_dir = (UPLOADS_DIR / str(user_id) / clean_id(memory_id)).resolve()
    try:
        target_dir.relative_to(UPLOADS_DIR.resolve())
    except ValueError:
        return
    if target_dir.exists():
        shutil.rmtree(target_dir)


def remove_uploads_for_user(user_id: int) -> None:
    target_dir = (UPLOADS_DIR / str(user_id)).resolve()
    try:
        target_dir.relative_to(UPLOADS_DIR.resolve())
    except ValueError:
        return
    if target_dir.exists():
        shutil.rmtree(target_dir)


class MemoryMapHandler(SimpleHTTPRequestHandler):
    server_version = "MemoryMap/1.0"

    def log_message(self, format: str, *args) -> None:
        print(f"[{utc_now()}] {self.address_string()} {format % args}")

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self.send_cors_headers()
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Accept")
        self.send_header("Access-Control-Max-Age", "86400")
        self.end_headers()

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/api/health":
            self.json_response({"ok": True, "service": "memory-map"})
        elif path.startswith("/api/photos/"):
            self.handle_photo(path)
        elif path == "/api/me":
            self.handle_me()
        elif path == "/api/memories":
            self.handle_list_memories()
        elif path.startswith("/api/"):
            self.json_response({"error": "接口不存在"}, status=404)
        else:
            self.serve_static(path)

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        if path == "/api/register":
            self.handle_register()
        elif path == "/api/login":
            self.handle_login()
        elif path == "/api/logout":
            self.handle_logout()
        elif path == "/api/memories":
            self.handle_create_memory()
        elif path == "/api/memories/reset":
            self.handle_reset_memories()
        else:
            self.json_response({"error": "接口不存在"}, status=404)

    def do_PUT(self) -> None:
        memory_id = self.memory_id_from_path()
        if not memory_id:
            self.json_response({"error": "接口不存在"}, status=404)
            return
        self.handle_update_memory(memory_id)

    def do_DELETE(self) -> None:
        memory_id = self.memory_id_from_path()
        if not memory_id:
            self.json_response({"error": "接口不存在"}, status=404)
            return
        self.handle_delete_memory(memory_id)

    def memory_id_from_path(self) -> str | None:
        path = urlparse(self.path).path
        prefix = "/api/memories/"
        if not path.startswith(prefix) or path == "/api/memories/reset":
            return None
        return unquote(path[len(prefix) :])

    def read_json(self) -> dict:
        length = int(self.headers.get("Content-Length", "0") or 0)
        if not length:
            return {}
        raw = self.rfile.read(length).decode("utf-8")
        return json.loads(raw)

    def send_cors_headers(self) -> None:
        origin = (self.headers.get("Origin") or "").rstrip("/")
        if not origin:
            return
        origins = allowed_origins()
        if "*" in origins or origin in origins:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Access-Control-Allow-Credentials", "true")
            self.send_header("Vary", "Origin")

    def json_response(self, payload: dict, status: int = 200, cookie_header: str | None = None) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_cors_headers()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        if cookie_header:
            self.send_header("Set-Cookie", cookie_header)
        self.end_headers()
        self.wfile.write(body)

    def serve_static(self, path: str) -> None:
        if path == "/":
            path = "/index.html"
        if path.startswith("/data/"):
            self.send_error(404)
            return

        target = (BASE_DIR / unquote(path).lstrip("/")).resolve()
        try:
            target.relative_to(BASE_DIR)
        except ValueError:
            self.send_error(404)
            return

        if not target.exists() or not target.is_file():
            self.send_error(404)
            return

        content = target.read_bytes()
        content_type = "application/manifest+json" if target.suffix == ".webmanifest" else mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        if target.suffix in {".html", ".css", ".js", ".svg", ".webmanifest"}:
            content_type += "; charset=utf-8"

        self.send_response(200)
        self.send_cors_headers()
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-cache" if target.suffix in {".html", ".js", ".css"} else "public, max-age=3600")
        self.end_headers()
        self.wfile.write(content)

    def handle_photo(self, path: str) -> None:
        user = self.require_user()
        if not user:
            return

        parts = path.split("/")
        if len(parts) != 6:
            self.send_error(404)
            return

        requested_user_id = parts[3]
        memory_id = clean_id(unquote(parts[4]))
        filename = Path(unquote(parts[5])).name

        if str(user["id"]) != requested_user_id:
            self.send_error(403)
            return

        target = (UPLOADS_DIR / requested_user_id / memory_id / filename).resolve()
        try:
            target.relative_to(UPLOADS_DIR.resolve())
        except ValueError:
            self.send_error(404)
            return

        if not target.exists() or not target.is_file():
            self.send_error(404)
            return

        content = target.read_bytes()
        content_type = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        self.send_response(200)
        self.send_cors_headers()
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "private, max-age=3600")
        self.end_headers()
        self.wfile.write(content)

    def current_user(self) -> sqlite3.Row | None:
        jar = cookies.SimpleCookie(self.headers.get("Cookie", ""))
        morsel = jar.get(SESSION_COOKIE)
        if not morsel:
            return None

        with db() as connection:
            row = connection.execute(
                """
                SELECT users.id, users.username
                FROM sessions
                JOIN users ON users.id = sessions.user_id
                WHERE sessions.token = ? AND sessions.expires_at > ?
                """,
                (morsel.value, int(time.time())),
            ).fetchone()
            return row

    def require_user(self) -> sqlite3.Row | None:
        user = self.current_user()
        if not user:
            self.json_response({"error": "请先登录"}, status=401)
            return None
        return user

    def is_secure_request(self) -> bool:
        forwarded_proto = self.headers.get("X-Forwarded-Proto", "").split(",")[0].strip().lower()
        return forwarded_proto == "https" or env_flag("MEMORY_MAP_COOKIE_SECURE")

    def cookie_for_token(self, token: str) -> str:
        parts = [
            f"{SESSION_COOKIE}={token}",
            "Path=/",
            f"Max-Age={SESSION_SECONDS}",
            "HttpOnly",
            f"SameSite={cookie_samesite()}",
        ]
        if self.is_secure_request() or cookie_samesite() == "None":
            parts.append("Secure")
        return "; ".join(parts)

    def clear_cookie(self) -> str:
        parts = [
            f"{SESSION_COOKIE}=",
            "Path=/",
            "Max-Age=0",
            "HttpOnly",
            f"SameSite={cookie_samesite()}",
        ]
        if self.is_secure_request() or cookie_samesite() == "None":
            parts.append("Secure")
        return "; ".join(parts)

    def handle_me(self) -> None:
        user = self.require_user()
        if not user:
            return
        self.json_response({"user": {"id": user["id"], "username": user["username"]}})

    def handle_register(self) -> None:
        try:
            payload = self.read_json()
            username = str(payload.get("username", "")).strip()
            password = str(payload.get("password", ""))

            if not (3 <= len(username) <= 32):
                raise ValueError("账号需要 3-32 个字符")
            if not re.fullmatch(r"[\w.@-]+", username, re.UNICODE):
                raise ValueError("账号只能包含字母、数字、下划线、点、@ 或短横线")
            if len(password) < 6:
                raise ValueError("密码至少 6 位")

            salt, password_hash = create_password_hash(password)
            with db() as connection:
                try:
                    cursor = connection.execute(
                        "INSERT INTO users(username, password_hash, salt, created_at) VALUES (?, ?, ?, ?)",
                        (username, password_hash, salt, utc_now()),
                    )
                except sqlite3.IntegrityError as exc:
                    raise ValueError("账号已存在") from exc

                user_id = int(cursor.lastrowid)
                seed_memories(connection, user_id)
                token = make_session(connection, user_id)

            self.json_response(
                {"user": {"id": user_id, "username": username}},
                cookie_header=self.cookie_for_token(token),
            )
        except ValueError as exc:
            self.json_response({"error": str(exc)}, status=400)
        except json.JSONDecodeError:
            self.json_response({"error": "请求格式不是 JSON"}, status=400)

    def handle_login(self) -> None:
        try:
            payload = self.read_json()
            username = str(payload.get("username", "")).strip()
            password = str(payload.get("password", ""))

            with db() as connection:
                user = connection.execute(
                    "SELECT id, username, password_hash, salt FROM users WHERE username = ?",
                    (username,),
                ).fetchone()

                if not user or not check_password(password, user["salt"], user["password_hash"]):
                    self.json_response({"error": "账号或密码不正确"}, status=401)
                    return

                token = make_session(connection, int(user["id"]))

            self.json_response(
                {"user": {"id": user["id"], "username": user["username"]}},
                cookie_header=self.cookie_for_token(token),
            )
        except json.JSONDecodeError:
            self.json_response({"error": "请求格式不是 JSON"}, status=400)

    def handle_logout(self) -> None:
        jar = cookies.SimpleCookie(self.headers.get("Cookie", ""))
        morsel = jar.get(SESSION_COOKIE)
        if morsel:
            with db() as connection:
                connection.execute("DELETE FROM sessions WHERE token = ?", (morsel.value,))
        self.json_response({"ok": True}, cookie_header=self.clear_cookie())

    def handle_list_memories(self) -> None:
        user = self.require_user()
        if not user:
            return

        with db() as connection:
            rows = connection.execute(
                """
                SELECT * FROM memories
                WHERE user_id = ?
                ORDER BY updated_at DESC, created_at DESC
                """,
                (user["id"],),
            ).fetchall()

        self.json_response({"memories": [row_to_memory(row) for row in rows]})

    def handle_create_memory(self) -> None:
        user = self.require_user()
        if not user:
            return

        try:
            payload = self.read_json()
            memory = validate_memory(payload)
            memory["photos"] = save_uploaded_photos(
                int(user["id"]),
                memory["id"],
                payload.get("newPhotos", []),
                memory["photos"],
            )
            now = utc_now()
            with db() as connection:
                connection.execute(
                    """
                    INSERT INTO memories(user_id, id, title, date, place, lat, lng, color, tags, story, photos, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        user["id"],
                        memory["id"],
                        memory["title"],
                        memory["date"],
                        memory["place"],
                        memory["lat"],
                        memory["lng"],
                        memory["color"],
                        json.dumps(memory["tags"], ensure_ascii=False),
                        memory["story"],
                        json.dumps(memory["photos"], ensure_ascii=False),
                        now,
                        now,
                    ),
                )
            self.json_response({"memory": memory}, status=201)
        except sqlite3.IntegrityError:
            self.json_response({"error": "这条记忆 ID 已存在"}, status=409)
        except ValueError as exc:
            self.json_response({"error": str(exc)}, status=400)
        except json.JSONDecodeError:
            self.json_response({"error": "请求格式不是 JSON"}, status=400)

    def handle_update_memory(self, memory_id: str) -> None:
        user = self.require_user()
        if not user:
            return

        try:
            payload = self.read_json()
            memory = validate_memory(payload, memory_id=memory_id)
            memory["photos"] = save_uploaded_photos(
                int(user["id"]),
                memory_id,
                payload.get("newPhotos", []),
                memory["photos"],
            )
            with db() as connection:
                cursor = connection.execute(
                    """
                    UPDATE memories
                    SET title = ?, date = ?, place = ?, lat = ?, lng = ?, color = ?, tags = ?, story = ?, photos = ?, updated_at = ?
                    WHERE user_id = ? AND id = ?
                    """,
                    (
                        memory["title"],
                        memory["date"],
                        memory["place"],
                        memory["lat"],
                        memory["lng"],
                        memory["color"],
                        json.dumps(memory["tags"], ensure_ascii=False),
                        memory["story"],
                        json.dumps(memory["photos"], ensure_ascii=False),
                        utc_now(),
                        user["id"],
                        memory_id,
                    ),
                )

                if cursor.rowcount == 0:
                    self.json_response({"error": "记忆不存在"}, status=404)
                    return

            self.json_response({"memory": memory})
        except ValueError as exc:
            self.json_response({"error": str(exc)}, status=400)
        except json.JSONDecodeError:
            self.json_response({"error": "请求格式不是 JSON"}, status=400)

    def handle_delete_memory(self, memory_id: str) -> None:
        user = self.require_user()
        if not user:
            return

        with db() as connection:
            cursor = connection.execute(
                "DELETE FROM memories WHERE user_id = ? AND id = ?",
                (user["id"], memory_id),
            )

        if cursor.rowcount == 0:
            self.json_response({"error": "记忆不存在"}, status=404)
            return

        remove_uploads_for_memory(int(user["id"]), memory_id)
        self.json_response({"ok": True})

    def handle_reset_memories(self) -> None:
        user = self.require_user()
        if not user:
            return

        with db() as connection:
            connection.execute("DELETE FROM memories WHERE user_id = ?", (user["id"],))
            remove_uploads_for_user(int(user["id"]))
            seed_memories(connection, int(user["id"]))
            rows = connection.execute(
                "SELECT * FROM memories WHERE user_id = ? ORDER BY updated_at DESC, created_at DESC",
                (user["id"],),
            ).fetchall()

        self.json_response({"memories": [row_to_memory(row) for row in rows]})


def main() -> None:
    parser = argparse.ArgumentParser(description="记忆地图本地服务器")
    default_host = os.environ.get("HOST") or ("0.0.0.0" if os.environ.get("PORT") else "127.0.0.1")
    default_port = int(os.environ.get("PORT", "8765"))
    parser.add_argument("--host", default=default_host)
    parser.add_argument("--port", type=int, default=default_port)
    args = parser.parse_args()

    init_db()
    server = ThreadingHTTPServer((args.host, args.port), MemoryMapHandler)
    print(f"记忆地图已启动：http://{args.host}:{args.port}")
    print(f"SQLite 数据库：{DB_PATH}")
    server.serve_forever()


if __name__ == "__main__":
    main()
