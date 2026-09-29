import os
from pathlib import Path
from threading import RLock

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from .runtime import cloud_enabled, cloud_data, current_user_id, user_directory

ROOT = Path(__file__).resolve().parents[2]
DATA = cloud_data() if cloud_enabled() else ROOT / "data"
DATA.mkdir(parents=True, exist_ok=True)
DATABASE_URL = os.environ.get("DATABASE_URL", f"sqlite:///{(DATA / 'planner.db').as_posix()}")


class Base(DeclarativeBase):
    pass


def make_engine(url):
    engine = create_engine(url, connect_args={"check_same_thread": False, "timeout": 30})

    @event.listens_for(engine, "connect")
    def configure_sqlite(connection, _):
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA busy_timeout=30000")

    return engine


engine = make_engine(DATABASE_URL)
SessionLocal = sessionmaker(engine, expire_on_commit=False)
_tenant_factories = {}
_migration_lock = RLock()


def tenant_factory(user_id):
    with _migration_lock:
        if user_id not in _tenant_factories:
            from alembic import command
            from alembic.config import Config
            directory = user_directory(user_id)
            directory.mkdir(parents=True, exist_ok=True)
            tenant_engine = make_engine(f"sqlite:///{(directory / 'planner.db').as_posix()}")
            config = Config(str(ROOT / "backend" / "alembic.ini"))
            try:
                with tenant_engine.begin() as connection:
                    config.attributes["connection"] = connection
                    command.upgrade(config, "head")
            except Exception:
                tenant_engine.dispose()
                raise
            _tenant_factories[user_id] = sessionmaker(tenant_engine, expire_on_commit=False)
        return _tenant_factories[user_id]


def clear_tenant_factories():
    with _migration_lock:
        for factory in _tenant_factories.values():
            factory.kw["bind"].dispose()
        _tenant_factories.clear()


def get_db():
    factory = tenant_factory(current_user_id()) if cloud_enabled() else SessionLocal
    with factory() as session:
        yield session
