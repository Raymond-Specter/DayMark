"""Small-server account registry, opaque sessions, and encrypted user keys."""
import hashlib
import hmac
import os
import secrets
import sqlite3
import time
from contextlib import contextmanager
from uuid import uuid4

from fastapi import HTTPException

from .runtime import cloud_data, current_user_id

COOKIE = "daymark_session"
SESSION_SECONDS = 7 * 24 * 60 * 60


@contextmanager
def registry():
    path = cloud_data() / "accounts.db"
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path, timeout=30)
    try:
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        with db:
            yield db
    finally:
        db.close()


def initialize():
    cipher()  # Missing encryption material must prevent a cloud startup.
    if len(os.environ.get("DAYMARK_INVITE_CODE", "")) < 16:
        raise RuntimeError("DAYMARK_INVITE_CODE must contain at least 16 characters")
    with registry() as db:
        db.execute("PRAGMA journal_mode=WAL")
        db.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY, username TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL, created_at INTEGER NOT NULL,
                deepseek_key TEXT NOT NULL DEFAULT '');
            CREATE TABLE IF NOT EXISTS sessions (
                token_hash TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id),
                expires_at INTEGER NOT NULL);
            CREATE TABLE IF NOT EXISTS auth_limits (
                key TEXT PRIMARY KEY, started_at INTEGER NOT NULL, attempts INTEGER NOT NULL);
        """)
        db.execute("DELETE FROM sessions WHERE expires_at <= ?", (int(time.time()),))
        db.execute("DELETE FROM auth_limits WHERE started_at < ?", (int(time.time()) - 900,))


def cipher():
    from cryptography.fernet import Fernet
    try:
        return Fernet(os.environ["DAYMARK_ENCRYPTION_KEY"].encode())
    except (KeyError, ValueError) as error:
        raise RuntimeError("A valid DAYMARK_ENCRYPTION_KEY is required") from error


def password_hash(password, salt=None):
    salt = salt or secrets.token_bytes(16)
    # OWASP's 32 MiB scrypt configuration, with three parallelization rounds.
    digest = hashlib.scrypt(password.encode(), salt=salt, n=32768, r=8, p=3,
                            dklen=32, maxmem=64 * 1024 * 1024)
    return f"scrypt${salt.hex()}${digest.hex()}"


def password_matches(password, encoded):
    _, salt, _ = encoded.split("$")
    return hmac.compare_digest(password_hash(password, bytes.fromhex(salt)), encoded)


def rate_limit(key):
    key = hashlib.sha256(key.encode()).hexdigest()
    now = int(time.time())
    with registry() as db:
        db.execute("BEGIN IMMEDIATE")
        row = db.execute("SELECT * FROM auth_limits WHERE key=?", (key,)).fetchone()
        if row and now - row["started_at"] < 900:
            if row["attempts"] >= 10:
                raise HTTPException(429, "Too many attempts. Please retry in 15 minutes.")
            db.execute("UPDATE auth_limits SET attempts=attempts+1 WHERE key=?", (key,))
        else:
            db.execute("INSERT OR REPLACE INTO auth_limits VALUES (?, ?, 1)", (key, now))


def register(username, password, invite):
    if not hmac.compare_digest(invite.encode(), os.environ.get("DAYMARK_INVITE_CODE", "").encode()):
        raise HTTPException(403, "Invalid invitation code")
    identifier = str(uuid4())
    encoded = password_hash(password)
    with registry() as db:
        db.execute("BEGIN IMMEDIATE")
        if db.execute("SELECT COUNT(*) FROM users").fetchone()[0] >= int(os.environ.get("DAYMARK_MAX_USERS", "100")):
            raise HTTPException(409, "Registration is currently full")
        try:
            db.execute("INSERT INTO users(id, username, password_hash, created_at) VALUES (?, ?, ?, ?)",
                       (identifier, username, encoded, int(time.time())))
        except sqlite3.IntegrityError:
            raise HTTPException(409, "Username already exists")
    return {"id": identifier, "username": username}


def login(username, password):
    with registry() as db:
        row = db.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
    # Equal-cost password work when the account does not exist.
    dummy = "scrypt$" + "00" * 16 + "$" + "00" * 32
    valid = password_matches(password, row["password_hash"] if row else dummy)
    if not row or not valid:
        raise HTTPException(401, "Incorrect username or password")
    return {"id": row["id"], "username": row["username"]}


def create_session(user_id):
    token = secrets.token_urlsafe(32)
    digest = hashlib.sha256(token.encode()).hexdigest()
    with registry() as db:
        db.execute("DELETE FROM sessions WHERE expires_at <= ?", (int(time.time()),))
        db.execute("INSERT INTO sessions VALUES (?, ?, ?)", (digest, user_id, int(time.time()) + SESSION_SECONDS))
    return token


def session_user(token):
    if not token or len(token) > 200:
        return None
    with registry() as db:
        row = db.execute("SELECT users.id, users.username FROM sessions JOIN users ON users.id=sessions.user_id "
                         "WHERE token_hash=? AND expires_at > ?",
                         (hashlib.sha256(token.encode()).hexdigest(), int(time.time()))).fetchone()
    return dict(row) if row else None


def revoke_session(token):
    with registry() as db:
        db.execute("DELETE FROM sessions WHERE token_hash=?", (hashlib.sha256((token or "").encode()).hexdigest(),))


def user_ids():
    with registry() as db:
        return [row[0] for row in db.execute("SELECT id FROM users")]


def save_api_key(value):
    with registry() as db:
        db.execute("UPDATE users SET deepseek_key=? WHERE id=?",
                   (cipher().encrypt(value.encode()).decode(), current_user_id()))


def read_api_key():
    with registry() as db:
        row = db.execute("SELECT deepseek_key FROM users WHERE id=?", (current_user_id(),)).fetchone()
    return cipher().decrypt(row[0].encode()).decode() if row and row[0] else ""
