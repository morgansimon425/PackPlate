"""The Alembic migrations must build exactly the schema in db/models.py."""

from alembic.autogenerate import compare_metadata
from alembic.runtime.migration import MigrationContext

from db.models import Base


def test_migrations_match_models(pg_engine):
    with pg_engine.connect() as conn:
        diff = compare_metadata(MigrationContext.configure(conn), Base.metadata)
    assert diff == [], f"models.py and migrations differ; add a migration: {diff}"
