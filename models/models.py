"""Small SQLite persistence layer for Student Hub."""
import sqlite3
import secrets
from datetime import datetime, timezone
from pathlib import Path

from werkzeug.security import generate_password_hash, check_password_hash

DB_PATH = Path(__import__("os").environ.get("STUDENT_HUB_DB_PATH", str(Path(__file__).resolve().parent.parent / "student_hub.db"))).expanduser()

SCHEMA = """
CREATE TABLE IF NOT EXISTS searches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    query TEXT NOT NULL,
    provider TEXT NOT NULL DEFAULT 'mock',
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_searches_query ON searches(query);

CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT UNIQUE NOT NULL,
    password_hash TEXT,
    name TEXT,
    google_id TEXT UNIQUE,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_users_google_id ON users(google_id);

CREATE TABLE IF NOT EXISTS login_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id),
    login_method TEXT NOT NULL,
    logged_in_at TEXT NOT NULL,
    ip_address TEXT,
    user_agent TEXT
);
CREATE INDEX IF NOT EXISTS idx_login_events_user ON login_events(user_id);
CREATE INDEX IF NOT EXISTS idx_login_events_time ON login_events(logged_in_at);

CREATE TABLE IF NOT EXISTS user_notes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id),
    title TEXT NOT NULL,
    content TEXT,
    category TEXT,
    tags TEXT,
    pinned INTEGER DEFAULT 0,
    favorite INTEGER DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_user_notes_user ON user_notes(user_id);

CREATE TABLE IF NOT EXISTS saved_resources (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id),
    title TEXT,
    url TEXT,
    resource_type TEXT,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_saved_resources_user ON saved_resources(user_id);
"""


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


# ---------------------------------------------------------------------------
# AI Teddy persistent conversations
# ---------------------------------------------------------------------------
CHAT_SCHEMA = """
CREATE TABLE IF NOT EXISTS chats (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title TEXT NOT NULL DEFAULT 'New Chat',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_chats_user_updated ON chats(user_id, updated_at DESC);

CREATE TABLE IF NOT EXISTS chat_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id INTEGER NOT NULL REFERENCES chats(id) ON DELETE CASCADE,
    sender TEXT NOT NULL CHECK(sender IN ('user','teddy')),
    content TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_chat_messages_chat_time ON chat_messages(chat_id, created_at ASC, id ASC);
"""


def init_chat_db():
    conn = get_connection()
    try:
        conn.executescript(CHAT_SCHEMA)
        conn.commit()
    finally:
        conn.close()


def create_chat(user_id: int, title: str = "New Chat"):
    now = datetime.now(timezone.utc).isoformat()
    conn = get_connection()
    try:
        cur = conn.execute(
            "INSERT INTO chats (user_id, title, created_at, updated_at) VALUES (?, ?, ?, ?)",
            (user_id, title.strip()[:100] or "New Chat", now, now),
        )
        conn.commit()
        return dict(conn.execute("SELECT * FROM chats WHERE id = ?", (cur.lastrowid,)).fetchone())
    finally:
        conn.close()


def list_user_chats(user_id: int):
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT id, title, created_at, updated_at FROM chats WHERE user_id = ? ORDER BY updated_at DESC",
            (user_id,),
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def get_user_chat(user_id: int, chat_id: int):
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT id, user_id, title, created_at, updated_at FROM chats WHERE id = ? AND user_id = ?",
            (chat_id, user_id),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def list_chat_messages(user_id: int, chat_id: int):
    conn = get_connection()
    try:
        rows = conn.execute(
            """SELECT m.id, m.sender, m.content, m.created_at
               FROM chat_messages m
               JOIN chats c ON c.id = m.chat_id
               WHERE m.chat_id = ? AND c.user_id = ?
               ORDER BY m.created_at ASC, m.id ASC""",
            (chat_id, user_id),
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def add_chat_message(user_id: int, chat_id: int, sender: str, content: str):
    if sender not in ("user", "teddy"):
        raise ValueError("Invalid chat sender")
    now = datetime.now(timezone.utc).isoformat()
    conn = get_connection()
    try:
        owned = conn.execute("SELECT id FROM chats WHERE id = ? AND user_id = ?", (chat_id, user_id)).fetchone()
        if not owned:
            return None
        cur = conn.execute(
            "INSERT INTO chat_messages (chat_id, sender, content, created_at) VALUES (?, ?, ?, ?)",
            (chat_id, sender, content, now),
        )
        conn.execute("UPDATE chats SET updated_at = ? WHERE id = ? AND user_id = ?", (now, chat_id, user_id))
        conn.commit()
        return dict(conn.execute("SELECT * FROM chat_messages WHERE id = ?", (cur.lastrowid,)).fetchone())
    finally:
        conn.close()


def rename_chat(user_id: int, chat_id: int, title: str):
    now = datetime.now(timezone.utc).isoformat()
    conn = get_connection()
    try:
        cur = conn.execute(
            "UPDATE chats SET title = ?, updated_at = ? WHERE id = ? AND user_id = ?",
            (title.strip()[:100] or "New Chat", now, chat_id, user_id),
        )
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def delete_chat(user_id: int, chat_id: int):
    conn = get_connection()
    try:
        conn.execute("DELETE FROM chat_messages WHERE chat_id = ? AND chat_id IN (SELECT id FROM chats WHERE user_id = ?)", (chat_id, user_id))
        cur = conn.execute("DELETE FROM chats WHERE id = ? AND user_id = ?", (chat_id, user_id))
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def init_db():
    conn = get_connection()
    try:
        conn.executescript(SCHEMA)
        conn.executescript(CHAT_SCHEMA)
        # Migrate databases created by older Student Hub versions.
        cols = {row[1] for row in conn.execute("PRAGMA table_info(users)").fetchall()}
        if "google_id" not in cols:
            conn.execute("ALTER TABLE users ADD COLUMN google_id TEXT")
        if "password_hash" not in cols:
            conn.execute("ALTER TABLE users ADD COLUMN password_hash TEXT")
        conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_users_google_id_unique ON users(google_id)")
        # Track the most recent successful login for each account.
        cols = {row[1] for row in conn.execute("PRAGMA table_info(users)").fetchall()}
        if "last_login_at" not in cols:
            conn.execute("ALTER TABLE users ADD COLUMN last_login_at TEXT")
        conn.commit()
    finally:
        conn.close()


def log_search(query: str, provider: str = "mock") -> None:
    try:
        conn = get_connection()
        conn.execute(
            "INSERT INTO searches (query, provider, created_at) VALUES (?, ?, ?)",
            (query, provider, datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()
        conn.close()
    except sqlite3.Error:
        pass


def create_user(name: str, email: str, password: str):
    now = datetime.now(timezone.utc).isoformat()
    password_hash = generate_password_hash(password)
    conn = get_connection()
    try:
        cur = conn.execute(
            "INSERT INTO users (name, email, password_hash, created_at) VALUES (?, ?, ?, ?)",
            (name.strip(), email.strip().lower(), password_hash, now),
        )
        conn.commit()
        return dict(conn.execute("SELECT * FROM users WHERE id = ?", (cur.lastrowid,)).fetchone())
    except sqlite3.IntegrityError:
        return None
    finally:
        conn.close()


def get_user_by_email(email: str):
    conn = get_connection()
    try:
        row = conn.execute("SELECT * FROM users WHERE lower(email) = lower(?)", (email.strip(),)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def get_user_by_google_id(google_id: str):
    conn = get_connection()
    try:
        row = conn.execute("SELECT * FROM users WHERE google_id = ?", (google_id,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def create_or_update_google_user(email: str, name: str, google_id: str):
    existing = get_user_by_google_id(google_id) or get_user_by_email(email)
    now = datetime.now(timezone.utc).isoformat()
    conn = get_connection()
    try:
        if existing:
            conn.execute(
                "UPDATE users SET name = ?, email = ?, google_id = ? WHERE id = ?",
                (name.strip() or existing.get("name"), email.strip().lower(), google_id, existing["id"]),
            )
            conn.commit()
            return dict(conn.execute("SELECT * FROM users WHERE id = ?", (existing["id"],)).fetchone())
        cur = conn.execute(
            "INSERT INTO users (name, email, password_hash, google_id, created_at) VALUES (?, ?, ?, ?, ?)",
            (name.strip() or email.split("@")[0], email.strip().lower(),
             generate_password_hash(secrets.token_urlsafe(32)), google_id, now),
        )
        conn.commit()
        return dict(conn.execute("SELECT * FROM users WHERE id = ?", (cur.lastrowid,)).fetchone())
    except sqlite3.IntegrityError:
        return None
    finally:
        conn.close()


def check_user_password(user, password: str) -> bool:
    return bool(user and user.get("password_hash") and check_password_hash(user["password_hash"], password))


def record_login(user_id: int, login_method: str, ip_address: str = "", user_agent: str = "") -> None:
    """Record a successful login and update the user's last-login timestamp."""
    now = datetime.now(timezone.utc).isoformat()
    conn = get_connection()
    try:
        conn.execute(
            "INSERT INTO login_events (user_id, login_method, logged_in_at, ip_address, user_agent) VALUES (?, ?, ?, ?, ?)",
            (user_id, login_method, now, ip_address, user_agent[:500]),
        )
        conn.execute("UPDATE users SET last_login_at = ? WHERE id = ?", (now, user_id))
        conn.commit()
    finally:
        conn.close()


def list_users_with_login_stats():
    conn = get_connection()
    try:
        rows = conn.execute("""
            SELECT u.id, u.name, u.email, u.created_at, u.last_login_at,
                   u.google_id,
                   COUNT(le.id) AS login_count,
                   MAX(le.logged_in_at) AS latest_login
            FROM users u
            LEFT JOIN login_events le ON le.user_id = u.id
            GROUP BY u.id
            ORDER BY COALESCE(u.last_login_at, u.created_at) DESC
        """).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def list_login_events(limit: int = 200):
    conn = get_connection()
    try:
        rows = conn.execute("""
            SELECT le.id, le.login_method, le.logged_in_at, le.ip_address,
                   le.user_agent, u.name, u.email
            FROM login_events le
            JOIN users u ON u.id = le.user_id
            ORDER BY le.logged_in_at DESC
            LIMIT ?
        """, (limit,)).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def list_user_login_events(user_id: int, limit: int = 50):
    conn = get_connection()
    try:
        rows = conn.execute("""
            SELECT id, login_method, logged_in_at, ip_address, user_agent
            FROM login_events
            WHERE user_id = ?
            ORDER BY logged_in_at DESC
            LIMIT ?
        """, (user_id, limit)).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()
