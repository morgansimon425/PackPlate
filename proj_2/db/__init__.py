"""Shared database schema for the API and the ingestion job.

    models.py      every table, with the one component allowed to write it
    session.py     engine + sessions from DATABASE_URL
    migrations/    Alembic versions; apply from proj_2/ with
                   alembic -c db/alembic.ini upgrade head
"""
