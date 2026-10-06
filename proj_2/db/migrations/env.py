"""Alembic environment: migrates the database named by DATABASE_URL.

A caller can pass its own connection via config.attributes["connection"]
(the test suite does this to migrate the test database).
"""

from alembic import context

from db.models import Base
from db.session import make_engine

config = context.config
target_metadata = Base.metadata


def run_migrations_offline():
    from db.session import database_url

    context.configure(url=database_url(), target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    connection = config.attributes.get("connection")
    if connection is not None:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()
        return
    engine = make_engine()
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
