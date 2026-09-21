import os
from pathlib import Path
import sqlite3
import subprocess
import sys


def test_upgrade_preserves_existing_planning_data(tmp_path):
    root = Path(__file__).resolve().parents[2]
    database = tmp_path / "migration.sqlite"
    env = {**os.environ, "DATABASE_URL": f"sqlite:///{database.as_posix()}"}
    command = [sys.executable, "-m", "alembic", "-c", str(root / "backend/alembic.ini")]
    subprocess.run([*command, "upgrade", "0001"], cwd=root, env=env, check=True, capture_output=True)
    with sqlite3.connect(database) as db:
        db.execute("INSERT INTO goals (id,name,description,status,priority,color,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?)",
                   ("existing-goal", "保留的目标", "原有数据", "active", 2, "#123456", "2026-01-01", "2026-01-01"))
    subprocess.run([*command, "upgrade", "head"], cwd=root, env=env, check=True, capture_output=True)
    subprocess.run([*command, "check"], cwd=root, env=env, check=True, capture_output=True)
    with sqlite3.connect(database) as db:
        assert db.execute("SELECT name,description FROM goals").fetchone() == ("保留的目标", "原有数据")
        assert db.execute("SELECT version_num FROM alembic_version").fetchone()[0] == "0005"
        assert "position" in [row[1] for row in db.execute("PRAGMA table_info(chat_messages)")]
        assert "message_id" in [row[1] for row in db.execute("PRAGMA table_info(chat_attachments)")]
