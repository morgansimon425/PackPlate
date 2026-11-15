"""Save and load Chat Rooms, invitations, and messages.

The route passes account IDs from M1 and commits when the whole request
succeeds. Room changes use the same transaction so they are saved together.
"""

from collections.abc import Iterable
from datetime import UTC, datetime
from typing import cast

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload, selectinload

from app.services.chat_room import ChatRoom, RoomStatus
from db.chat_models import ChatInvitation, ChatMessage, ChatRoomMember, ChatRoomRecord


def _load_room(db: Session, room_id: int, *, for_write: bool = False) -> ChatRoomRecord:
    # Lock the room while we read its members or make a change.
    room = db.get(
        ChatRoomRecord,
        room_id,
        options=(
            selectinload(ChatRoomRecord.memberships),
            selectinload(ChatRoomRecord.invitations),
        ),
        with_for_update={"read": not for_write},
        populate_existing=True,
    )
    if room is None:
        raise LookupError("Chat Room not found.")
    return room


def _room_rules(room: ChatRoomRecord) -> ChatRoom:
    # Give the service the current members, pending invites, and room status.
    return ChatRoom(
        member_ids=set(room.member_ids),
        pending_invitee_ids={
            invite.invitee_id
            for invite in room.invitations
            if invite.status == "pending"
        },
        status=cast(RoomStatus, room.status),
    )


def _invited_room(
    db: Session, invitation_id: int, user_id: int
) -> tuple[ChatRoomRecord, ChatInvitation]:
    invitation = db.get(ChatInvitation, invitation_id)
    if invitation is None:
        raise LookupError("Chat Room invitation not found.")
    if invitation.invitee_id != user_id:
        raise PermissionError("This invitation is for another user.")

    # Read the invitation again after locking the room in case it just changed.
    room = _load_room(db, invitation.room_id, for_write=True)
    current_invitation = next(
        inv for inv in room.invitations if inv.id == invitation_id
    )
    return room, current_invitation


# Create a Chat Room and save one invitation for each person picked.
def create_room(
    db: Session, creator_id: int, invitee_ids: Iterable[int]
) -> ChatRoomRecord:
    """Save a pending room with verified M1 account IDs. Raises ValueError on bad invites."""
    invitees = set(invitee_ids)
    if not invitees or creator_id in invitees:
        raise ValueError(
            "Invite at least one other user and leave yourself off the list."
        )

    state = ChatRoom(member_ids={creator_id}, pending_invitee_ids=invitees)
    room = ChatRoomRecord(
        status=state.status,
        memberships=[ChatRoomMember(user_id=creator_id)],
        invitations=[
            ChatInvitation(invitee_id=user_id, status="pending")
            for user_id in sorted(invitees)
        ],
    )
    db.add(room)
    db.flush()
    return room


# Get the Chat Rooms the user has joined.
def list_rooms(db: Session, user_id: int) -> list[ChatRoomRecord]:
    """Return the user's rooms with the current members loaded."""
    rooms = (
        select(ChatRoomRecord)
        .join(ChatRoomRecord.memberships)
        .where(ChatRoomMember.user_id == user_id)
        .options(joinedload(ChatRoomRecord.memberships))
        .order_by(ChatRoomRecord.id)
        .execution_options(populate_existing=True)
    )
    return list(db.scalars(rooms).unique())


def get_room(db: Session, room_id: int, user_id: int) -> ChatRoomRecord:
    """Load a room for a joined member. Raises LookupError or PermissionError."""
    room = _load_room(db, room_id)
    if not _room_rules(room).can_read_messages(user_id):
        raise PermissionError("This user is not a Chat Room member.")
    return room


def list_invitations(db: Session, user_id: int) -> list[ChatInvitation]:
    """Return pending invitations for this account."""
    invitations = (
        select(ChatInvitation)
        .where(ChatInvitation.invitee_id == user_id, ChatInvitation.status == "pending")
        .order_by(ChatInvitation.id)
    )
    return list(db.scalars(invitations))


# Move the invitee to the member list when they accept.
def accept_invitation(db: Session, invitation_id: int, user_id: int) -> ChatRoomRecord:
    """Save an acceptance and return the room. Raises LookupError or PermissionError."""
    room, invitation = _invited_room(db, invitation_id, user_id)
    state = _room_rules(room)

    # If they already joined, the same request should leave the room as is.
    if invitation.status == "accepted" and state.can_read_messages(user_id):
        return room

    state.accept_invitation(user_id)
    invitation.status = "accepted"
    room.memberships.append(ChatRoomMember(user_id=user_id))
    room.status = state.status
    db.flush()
    return room


def decline_invitation(db: Session, invitation_id: int, user_id: int) -> None:
    """Save a decline without adding a member. Raises LookupError or PermissionError."""
    room, invitation = _invited_room(db, invitation_id, user_id)
    if invitation.status == "declined":
        return

    _room_rules(room).decline_invitation(user_id)
    invitation.status = "declined"
    db.flush()


# Save the change when a member exits the Chat Room.
def leave_room(db: Session, room_id: int, member_id: int) -> None:
    """Remove a member and save the room status. Raises LookupError or PermissionError."""
    room = _load_room(db, room_id, for_write=True)
    state = _room_rules(room)
    state.leave(member_id)
    room.memberships[:] = [
        member for member in room.memberships if member.user_id in state.member_ids
    ]
    room.status = state.status

    # Keep the invitation records so we know why they are no longer pending.
    if state.status == "inactive":
        for invitation in room.invitations:
            if invitation.status == "pending":
                invitation.status = "cancelled"
    db.flush()


def list_messages(db: Session, room_id: int, user_id: int) -> list[ChatMessage]:
    """Return a member's room history in order. Raises LookupError or PermissionError."""
    get_room(db, room_id, user_id)
    messages = (
        select(ChatMessage)
        .where(ChatMessage.room_id == room_id)
        .order_by(ChatMessage.created_at, ChatMessage.id)
    )
    return list(db.scalars(messages))


def add_message(db: Session, room_id: int, sender_id: int, text: str) -> ChatMessage:
    """Save a member's message in an active room. Raises ValueError on bad text or room status."""
    room = _load_room(db, room_id, for_write=True)
    state = _room_rules(room)
    if not state.can_read_messages(sender_id):
        raise PermissionError("This user is not a Chat Room member.")
    if not state.can_send_messages(sender_id):
        raise ValueError("Messages can only be sent in an active Chat Room.")
    if not text.strip():
        raise ValueError("The message cannot be blank.")

    # Use the account ID from login and give the message a time on the backend.
    message = ChatMessage(
        room_id=room_id, sender_id=sender_id, text=text, created_at=datetime.now(UTC)
    )
    db.add(message)
    db.flush()
    return message


# Called before an account is deleted (M1's DELETE /auth/me).
def leave_all_rooms(db: Session, user_id: int) -> None:
    """Have the user leave every room they've joined, using the normal rules.

    Deleting the account would otherwise drop their memberships at the database
    level and skip leave(), leaving an "active" room with one member (which the
    rules then refuse to load) or a pending room with nobody in it.
    """
    for room in list_rooms(db, user_id):
        leave_room(db, room.id, user_id)
