"""Run the ingestion pipeline once: fetch -> parse -> normalize -> write.

Usage (from proj_2/):  python -m ingestion.run
"""

from ingestion.fetch import fetch
from ingestion.normalize import normalize
from ingestion.parse import parse
from ingestion.write import write


def main():
    write(normalize(parse(fetch())))


if __name__ == "__main__":
    main()
