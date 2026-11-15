"""Chat Room routes (M4): rooms, invitations, messages, and finding people.

Every route needs a logged-in user (M1's current_user, 401 otherwise); the
account comes from the session cookie, never from the request body. The rules
live in services/chat_room.py and the queries in repositories/chat_rooms.py,
which only flush; each route commits once the whole change has worked.

Errors from the repository map to:
    LookupError      404  room, invitation, or user not found
    PermissionError  403  not a member, or someone else's invitation
    ValueError       409  the room's status doesn't allow it (pending/inactive)
"""

from collections.abc import Callable
from datetime import UTC

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.deps import current_user, get_db
from app.repositories import chat_rooms as chat_repo
from app.repositories import users as users_repo
from app.schemas.chat_room import (
    ChatInvitationOut,
    ChatMessageCreate,
    ChatMessageOut,
    ChatRoomCreate,
    ChatRoomOut,
    OpenToChatOut,
    OpenToChatPerson,
    OpenToChatUpdate,
)
from app.services.auth import normalize_username, username_problem
from db.chat_models import ChatMessage, ChatRoomRecord
from db.models import User

router = APIRouter(prefix="/chat", tags=["chat"])


def _commit[T](db: Session, change: Callable[..., T], *args) -> T:
    """Run one repository change and commit it, or roll back and answer with an error."""
    try:
        result = change(db, *args)
    except LookupError as e:
        db.rollback()
        raise HTTPException(status_code=404, detail=str(e)) from e
    except PermissionError as e:
        db.rollback()
        raise HTTPException(status_code=403, detail=str(e)) from e
    except ValueError as e:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(e)) from e
    db.commit()
    return result


def _room_out(room: ChatRoomRecord) -> ChatRoomOut:
    return ChatRoomOut(id=room.id, status=room.status, member_ids=room.member_ids)


def _message_out(message: ChatMessage) -> ChatMessageOut:
    return ChatMessageOut(
        id=message.id,
        text=message.text,
        sender_id=message.sender_id,
        created_at=message.created_at.astimezone(UTC),
    )


# Get the Chat Rooms the logged-in user is part of.
@router.get("/rooms", response_model=list[ChatRoomOut])
def list_rooms(user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Return the rooms the current user has joined."""
    return [_room_out(room) for room in chat_repo.list_rooms(db, user.id)]


# Create a Chat Room and send an invitation to each selected user.
@router.post("/rooms", response_model=ChatRoomOut, status_code=201)
def create_room(
    request: ChatRoomCreate,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    """Create a pending room from the selected account IDs.

    400 if the creator invites themselves, 404 if an invited account doesn't exist.
    """
    if user.id in request.invitee_ids:
        raise HTTPException(status_code=400, detail="you can't invite yourself")
    for invitee_id in request.invitee_ids:
        if users_repo.get_by_id(db, invitee_id) is None:
            raise HTTPException(status_code=404, detail=f"user {invitee_id} not found")
    room = _commit(db, chat_repo.create_room, user.id, request.invitee_ids)
    return _room_out(room)


# Get a Chat Room when a member opens it.
@router.get("/rooms/{room_id}", response_model=ChatRoomOut)
def get_room(
    room_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)
):
    """Return the room's status and joined members."""
    return _room_out(_commit(db, chat_repo.get_room, room_id, user.id))


# Have the logged-in member exit the Chat Room.
@router.post("/rooms/{room_id}/leave", status_code=204, response_class=Response)
def leave_room(
    room_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)
):
    """Remove the current member and update the room status."""
    _commit(db, chat_repo.leave_room, room_id, user.id)
    return Response(status_code=204)


# Get the invitations sent to the logged-in user.
@router.get("/invitations", response_model=list[ChatInvitationOut])
def list_invitations(user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Return the current user's pending invitations."""
    return [
        ChatInvitationOut(id=invitation.id, room_id=invitation.room_id)
        for invitation in chat_repo.list_invitations(db, user.id)
    ]


# Accept an invitation and join the Chat Room.
@router.post("/invitations/{invitation_id}/accept", response_model=ChatRoomOut)
def accept_invitation(
    invitation_id: int,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    """Accept the current user's invitation and return the updated room."""
    room = _commit(db, chat_repo.accept_invitation, invitation_id, user.id)
    return _room_out(room)


# Decline an invitation without joining the Chat Room.
@router.post(
    "/invitations/{invitation_id}/decline", status_code=204, response_class=Response
)
def decline_invitation(
    invitation_id: int,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    """Decline the current user's invitation."""
    _commit(db, chat_repo.decline_invitation, invitation_id, user.id)
    return Response(status_code=204)


# Get the messages a member can see in the Chat Room.
@router.get("/rooms/{room_id}/messages", response_model=list[ChatMessageOut])
def list_messages(
    room_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)
):
    """Return message history for a current member, even if the room is inactive."""
    messages = _commit(db, chat_repo.list_messages, room_id, user.id)
    return [_message_out(message) for message in messages]


# Send a message in an active Chat Room.
@router.post(
    "/rooms/{room_id}/messages", response_model=ChatMessageOut, status_code=201
)
def send_message(
    room_id: int,
    request: ChatMessageCreate,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    """Save the text with the signed-in sender and return the saved message."""
    message = _commit(db, chat_repo.add_message, room_id, user.id, request.text)
    return _message_out(message)


@router.get("/users/{username}", response_model=OpenToChatPerson)
def lookup_user(
    username: str, user: User = Depends(current_user), db: Session = Depends(get_db)
):
    """Find another account by exact username, ignoring case.

    Returns the account ID and username even if Open to Chat is off.
    400 for an invalid username or 404 when no other account matches.
    """
    username = normalize_username(username)
    problem = username_problem(username)
    if problem:
        raise HTTPException(status_code=400, detail=problem)
    person = users_repo.get_by_username(db, username)
    if person is None or person.id == user.id:
        raise HTTPException(status_code=404, detail="user not found")
    return OpenToChatPerson(id=person.id, username=person.username)


# Turn the logged-in user's Open to Chat setting on or off.
@router.put("/open-to-chat", response_model=OpenToChatOut)
def set_open_to_chat(
    request: OpenToChatUpdate,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    """Show or hide the current user on the Open to Chat list (off by default)."""
    users_repo.set_open_to_chat(db, user, request.open_to_chat)
    return OpenToChatOut(open_to_chat=user.open_to_chat)


# Get the people who can be invited from the Open to Chat list.
@router.get("/open-to-chat", response_model=list[OpenToChatPerson])
def list_open_to_chat(
    user: User = Depends(current_user), db: Session = Depends(get_db)
):
    """Everyone else with Open to Chat on, by username."""
    people = db.scalars(
        select(User)
        .where(User.open_to_chat.is_(True), User.id != user.id)
        .order_by(User.username)
    )
    return [
        OpenToChatPerson(id=person.id, username=person.username) for person in people
    ]
