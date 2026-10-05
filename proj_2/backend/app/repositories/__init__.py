"""Data access layer: the only code in the API that queries Postgres.

Single writer per table: the API writes crowd reports only. Menu and
nutrition tables are written by ingestion/ and are read-only here.
"""
