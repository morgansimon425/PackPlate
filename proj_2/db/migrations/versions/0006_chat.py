"""group chat: rooms, members, invitations, messages (M4)

Revision ID: 0006
Revises: 0005
Create Date: 2026-11-09
"""

import sqlalchemy as sa
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "chat_rooms",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(10), nullable=False),
        sa.CheckConstraint(
            "status IN ('pending', 'active', 'inactive')", name="ck_chat_rooms_status"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "chat_room_members",
        sa.Column("room_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["room_id"], ["chat_rooms.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("room_id", "user_id"),
    )
    op.create_index("ix_chat_room_members_user_id", "chat_room_members", ["user_id"])
    op.create_table(
        "chat_invitations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("room_id", sa.Integer(), nullable=False),
        sa.Column("invitee_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(10), nullable=False),
        sa.CheckConstraint(
            "status IN ('pending', 'accepted', 'declined', 'cancelled')",
            name="ck_chat_invitations_status",
        ),
        sa.ForeignKeyConstraint(["room_id"], ["chat_rooms.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["invitee_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "room_id", "invitee_id", name="uq_chat_invitation_room_user"
        ),
    )
    op.create_index(
        "ix_chat_invitations_invitee_id", "chat_invitations", ["invitee_id"]
    )
    op.create_table(
        "chat_messages",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("room_id", sa.Integer(), nullable=False),
        sa.Column("sender_id", sa.Integer(), nullable=True),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["room_id"], ["chat_rooms.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["sender_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_chat_messages_room_time_id",
        "chat_messages",
        ["room_id", "created_at", "id"],
    )


def downgrade():
    op.drop_table("chat_messages")
    op.drop_table("chat_invitations")
    op.drop_table("chat_room_members")
    op.drop_table("chat_rooms")
