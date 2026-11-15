"""Tables for Chat Rooms, members, invitations, and messages (M4). Writer: backend.

Imported at the bottom of db/models.py, so these tables are on Base.metadata
for Alembic and the tests. Every account ID is users.id from M1: memberships and
invitations go when the account is deleted; a message stays, with sender_id set
to NULL ("deleted user"), so other members keep their history.
"""

from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.models import Base


class ChatRoomRecord(Base):
    """One saved Chat Room and its status. Writer: backend."""

    __tablename__ = "chat_rooms"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'active', 'inactive')", name="ck_chat_rooms_status"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    status: Mapped[str] = mapped_column(String(10))
    memberships: Mapped[list["ChatRoomMember"]] = relationship(
        cascade="all, delete-orphan"
    )
    invitations: Mapped[list["ChatInvitation"]] = relationship(
        cascade="all, delete-orphan"
    )

    @property
    def member_ids(self) -> list[int]:
        """Return the account IDs of people who have joined the Chat Room."""
        return sorted(member.user_id for member in self.memberships)


class ChatRoomMember(Base):
    """One account that has joined a Chat Room. Writer: backend."""

    __tablename__ = "chat_room_members"

    # The two IDs together stop the same person from joining a room twice.
    room_id: Mapped[int] = mapped_column(
        ForeignKey("chat_rooms.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True, index=True
    )


class ChatInvitation(Base):
    """An invitation and its response, so retries can find it. Writer: backend."""

    __tablename__ = "chat_invitations"
    __table_args__ = (
        UniqueConstraint("room_id", "invitee_id", name="uq_chat_invitation_room_user"),
        CheckConstraint(
            "status IN ('pending', 'accepted', 'declined', 'cancelled')",
            name="ck_chat_invitations_status",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    room_id: Mapped[int] = mapped_column(
        ForeignKey("chat_rooms.id", ondelete="CASCADE")
    )
    invitee_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    status: Mapped[str] = mapped_column(String(10))


class ChatMessage(Base):
    """One message saved in a Chat Room. Writer: backend."""

    __tablename__ = "chat_messages"
    __table_args__ = (
        Index("ix_chat_messages_room_time_id", "room_id", "created_at", "id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    room_id: Mapped[int] = mapped_column(
        ForeignKey("chat_rooms.id", ondelete="CASCADE")
    )
    # Keep the sender ID with the message even after the sender leaves the room.
    # NULL once the sender deletes their account.
    sender_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    text: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
