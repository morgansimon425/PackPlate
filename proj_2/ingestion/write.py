"""Write: store menu and nutrition data in Postgres.

Single writer per table: this is the only code that writes menu and
nutrition tables. The API only reads them.
"""


def write(records):
    """Persist labelled records."""
