"""Request and response fields for Chat Rooms and Open to Chat."""

from typing import Annotated

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator

from app.services.chat_room import RoomStatus

# M1's account ID: users.id, a positive integer.
type AccountId = Annotated[int, Field(strict=True, gt=0)]


class ChatRoomCreate(BaseModel):
    """The user IDs the creator sends when starting a Chat Room."""

    model_config = ConfigDict(extra="forbid")

    # Send the IDs of the people the creator picked by username.
    invitee_ids: list[AccountId] = Field(min_length=1)

    @field_validator("invitee_ids")
    @classmethod
    def remove_duplicate_invitees(cls, invitee_ids: list[AccountId]) -> list[AccountId]:
        """Keep the first occurrence of each invited user ID."""
        return list(dict.fromkeys(invitee_ids))


class ChatRoomOut(BaseModel):
    """A Chat Room and the users who have joined it."""

    # Use the room ID to open the Chat Room or get its messages.
    id: int
    status: RoomStatus
    # Only include people who have joined. Pending invitations are separate.
    member_ids: list[AccountId]


class ChatInvitationOut(BaseModel):
    """A pending invitation the signed-in user can accept or decline."""

    id: int
    # Use this ID to find the Chat Room the invitation is for.
    room_id: int


class ChatMessageCreate(BaseModel):
    """The text a member sends to an active Chat Room."""

    # The backend gets the sender from login. The user only sends the message text.
    model_config = ConfigDict(extra="forbid")
    text: str = Field(pattern=r"\S")


class ChatMessageOut(BaseModel):
    """A saved message with its sender and the UTC time it was sent."""

    id: int
    text: str
    sender_id: AccountId | None  # null once the sender deletes their account
    # Include the time zone so the frontend can show the right time.
    created_at: AwareDatetime


class OpenToChatUpdate(BaseModel):
    """The setting a signed-in user sends to turn Open to Chat on or off."""

    model_config = ConfigDict(extra="forbid")

    # True puts the user on the Open to Chat list. False takes them off.
    open_to_chat: bool = Field(strict=True)


class OpenToChatOut(BaseModel):
    """The signed-in user's Open to Chat setting after a change."""

    open_to_chat: bool


class OpenToChatPerson(BaseModel):
    """The ID and username of an account that can be invited to a Chat Room."""

    id: AccountId
    username: str
