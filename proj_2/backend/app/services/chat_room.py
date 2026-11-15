"""Keep track of who has joined a Chat Room and what they can do."""

from dataclasses import dataclass, field
from typing import Literal
from uuid import UUID

type UserId = int | str | UUID
type RoomStatus = Literal["pending", "active", "inactive"]


@dataclass
class ChatRoom:
    """Track the members, pending invitations, and status of one Chat Room."""

    # member_ids holds the account IDs of the people who have joined.
    # When we first make a Chat Room, this only has the creator's ID.
    member_ids: set[UserId]

    # pending_invitee_ids holds the account IDs of people who still need to respond.
    # We use the IDs from M1 so a username change does not affect the Chat Room.
    pending_invitee_ids: set[UserId] = field(default_factory=set)

    # A room starts pending, becomes active with two members, and becomes
    # inactive when fewer than two members are left after someone exits.
    status: RoomStatus = "pending"

    def __post_init__(self) -> None:
        # Copy both sets so changing the Chat Room does not change the original lists.
        self.member_ids = set(self.member_ids)
        self.pending_invitee_ids = set(self.pending_invitee_ids)

        if self.member_ids & self.pending_invitee_ids:
            raise ValueError("A member cannot also have a pending invitation.")

        member_count = len(self.member_ids)
        if self.status not in ("pending", "active", "inactive"):
            raise ValueError("Unknown Chat Room status.")
        if self.status == "pending" and member_count != 1:
            raise ValueError("A pending Chat Room must have exactly one member.")
        if self.status == "active" and member_count < 2:
            raise ValueError("An active Chat Room must have at least two members.")
        if self.status == "inactive" and (member_count > 1 or self.pending_invitee_ids):
            raise ValueError(
                "An inactive Chat Room can have at most one member and no pending invitations."
            )

    def accept_invitation(self, user_id: UserId) -> None:
        """Add an invited user to the room. Raises PermissionError without an invite."""
        # If this user already joined, accepting again leaves the room as is.
        if user_id in self.member_ids:
            return
        if user_id not in self.pending_invitee_ids:
            raise PermissionError("This user has no pending invitation.")

        # Move the user from the invitation list to the member list.
        self.pending_invitee_ids.remove(user_id)
        self.member_ids.add(user_id)
        self.status = "active"

    def decline_invitation(self, user_id: UserId) -> None:
        """Remove a pending invitation. Raises PermissionError without an invite."""
        if user_id not in self.pending_invitee_ids:
            raise PermissionError("This user has no pending invitation.")

        # The user did not join, so the members and room status stay the same.
        self.pending_invitee_ids.remove(user_id)

    def leave(self, member_id: UserId) -> None:
        """Remove a member and close the room if fewer than two people remain."""
        if member_id not in self.member_ids:
            raise PermissionError("This user is not a Chat Room member.")

        self.member_ids.remove(member_id)
        if len(self.member_ids) < 2:
            # Clear the pending invitations so nobody can join the inactive room.
            self.status = "inactive"
            self.pending_invitee_ids.clear()

    def can_read_messages(self, user_id: UserId) -> bool:
        """Check if the user is still a member and can see the room's messages."""
        return user_id in self.member_ids

    def can_send_messages(self, user_id: UserId) -> bool:
        """Check if the user is a member of an active room and can send messages."""
        return self.status == "active" and self.can_read_messages(user_id)
