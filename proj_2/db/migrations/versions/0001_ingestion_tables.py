"""ingestion tables: locations, hours, menus, items, nutrition, ingest runs

Revision ID: 0001
Revises:
Create Date: 2026-10-06
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

TZ = sa.DateTime(timezone=True)


def upgrade():
    op.create_table(
        "locations",
        sa.Column("id", sa.Integer(), autoincrement=False, nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("dining_slug", sa.String(100), nullable=True),
        sa.Column("updated_at", TZ, nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "ingest_runs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("started_at", TZ, nullable=False),
        sa.Column("finished_at", TZ, nullable=True),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("options", postgresql.JSONB(), nullable=False),
        sa.Column("stats", postgresql.JSONB(), nullable=False),
        sa.Column("errors", postgresql.JSONB(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ingest_runs_started_at", "ingest_runs", ["started_at"])
    op.create_table(
        "hours_days",
        sa.Column("location_id", sa.Integer(), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("status", sa.String(10), nullable=False),
        sa.Column("windows", postgresql.JSONB(), nullable=False),
        sa.Column("raw_text", sa.Text(), nullable=True),
        sa.Column("fetched_at", TZ, nullable=False),
        sa.ForeignKeyConstraint(["location_id"], ["locations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("location_id", "date"),
    )
    op.create_table(
        "menus",
        sa.Column("id", sa.Integer(), autoincrement=False, nullable=False),
        sa.Column("location_id", sa.Integer(), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("meal", sa.String(50), nullable=False),
        sa.Column("fetched_at", TZ, nullable=True),
        sa.ForeignKeyConstraint(["location_id"], ["locations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_menus_location_id", "menus", ["location_id"])
    op.create_index("ix_menus_date", "menus", ["date"])
    op.create_table(
        "nutrition",
        sa.Column("key", sa.String(500), nullable=False),
        sa.Column("location_id", sa.Integer(), nullable=False),
        sa.Column("source_detail_oid", sa.Integer(), nullable=False),
        sa.Column("serving_size", sa.String(200), nullable=True),
        sa.Column("calories", sa.Float(), nullable=True),
        sa.Column("protein_g", sa.Float(), nullable=True),
        sa.Column("fat_g", sa.Float(), nullable=True),
        sa.Column("carbs_g", sa.Float(), nullable=True),
        sa.Column("sodium_mg", sa.Float(), nullable=True),
        sa.Column("nutrients_raw", postgresql.JSONB(), nullable=False),
        sa.Column("ingredients", sa.Text(), nullable=True),
        sa.Column("contains", postgresql.JSONB(), nullable=False),
        sa.Column("missing_fields", postgresql.JSONB(), nullable=False),
        sa.Column("fetched_at", TZ, nullable=False),
        sa.ForeignKeyConstraint(["location_id"], ["locations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("key"),
    )
    op.create_index("ix_nutrition_location_id", "nutrition", ["location_id"])
    op.create_table(
        "menu_items",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("menu_id", sa.Integer(), nullable=False),
        sa.Column("detail_oid", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(300), nullable=False),
        sa.Column("course", sa.String(200), nullable=True),
        sa.Column("serving_size", sa.String(200), nullable=True),
        sa.Column("traits_raw", postgresql.JSONB(), nullable=False),
        sa.Column("allergens", postgresql.JSONB(), nullable=False),
        sa.Column("diets", postgresql.JSONB(), nullable=False),
        sa.Column("unrecognized_traits", postgresql.JSONB(), nullable=False),
        sa.Column("nutrition_key", sa.String(500), nullable=True),
        sa.ForeignKeyConstraint(["menu_id"], ["menus.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["nutrition_key"], ["nutrition.key"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_menu_items_menu_id", "menu_items", ["menu_id"])


def downgrade():
    op.drop_table("menu_items")
    op.drop_table("nutrition")
    op.drop_table("menus")
    op.drop_table("hours_days")
    op.drop_table("ingest_runs")
    op.drop_table("locations")
