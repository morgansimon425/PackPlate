"""Helpers around Alembic for code that needs the schema (the job, the tests)."""

from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import Connection, Engine

ALEMBIC_INI = Path(__file__).parent / "alembic.ini"


def alembic_config() -> Config:
    return Config(str(ALEMBIC_INI))


def upgrade(connection: Connection, revision: str = "head"):
    cfg = alembic_config()
    cfg.attributes["connection"] = connection
    command.upgrade(cfg, revision)


def check_current(engine: Engine):
    """Raise if the database isn't migrated to the revision this code expects."""
    head = ScriptDirectory.from_config(alembic_config()).get_current_head()
    with engine.connect() as conn:
        current = MigrationContext.configure(conn).get_current_revision()
    if current != head:
        raise RuntimeError(
            f"database schema is at revision {current}, code expects {head}; "
            "run `alembic -c db/alembic.ini upgrade head` from proj_2/"
        )
