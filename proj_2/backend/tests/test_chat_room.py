# This file tests the functionality of using the chat room. Milestone 4

import pytest


# Test creating a Chat Room with only the creator as a member
def test_room_with_only_creator_is_pending():
    from app.services.chat_room import ChatRoom

    # Create a Chat Room with one member and one invitee.
    room = ChatRoom(member_ids={1}, pending_invitee_ids={2})

    # Check that the creator is the only member and the Chat Room starts pending.
    assert room.member_ids == {1}
    assert room.status == "pending"


# Test counting members with pending invitations (only joined users are counted)
def test_pending_invitations_do_not_count_as_members():
    from app.services.chat_room import ChatRoom

    # Create a Chat Room with one member and two pending invitations.
    room = ChatRoom(member_ids={1}, pending_invitee_ids={2, 3})

    # Check that neither invitee counts as a member yet.
    assert room.member_ids == {1}
    assert room.pending_invitee_ids == {2, 3}
    assert room.status == "pending"


# Test accepting the first Chat Room invitation (Chat Room becomes active)
def test_accepting_first_invitation_makes_room_active():
    from app.services.chat_room import ChatRoom

    # Set up a pending Chat Room with one member and one invitee.
    room = ChatRoom(member_ids={1}, pending_invitee_ids={2}, status="pending")

    # Have user 2 accept the invitation.
    room.accept_invitation(user_id=2)

    # Check that the user joined and the Chat Room is active.
    assert room.member_ids == {1, 2}
    assert room.pending_invitee_ids == set()
    assert room.status == "active"


# Test declining a Chat Room invitation (the user does not join)
def test_declining_invitation_keeps_room_pending():
    from app.services.chat_room import ChatRoom

    # Set up a pending Chat Room with one member and two invitees.
    room = ChatRoom(member_ids={1}, pending_invitee_ids={2, 3}, status="pending")

    # Have user 2 decline the invitation.
    room.decline_invitation(user_id=2)

    # Check that only user 3's invitation is pending and the room status stays the same.
    assert room.member_ids == {1}
    assert room.pending_invitee_ids == {3}
    assert room.status == "pending"


# Test accepting the same Chat Room invitation twice (the user only joins once)
def test_accepting_invitation_twice():
    from app.services.chat_room import ChatRoom

    # Set up a pending Chat Room with one member and one invitee.
    room = ChatRoom(member_ids={1}, pending_invitee_ids={2}, status="pending")

    # Accept the invitation the first time.
    room.accept_invitation(user_id=2)
    assert room.member_ids == {1, 2}
    assert room.pending_invitee_ids == set()
    assert room.status == "active"

    # Attempt to accept the same invitation again.
    room.accept_invitation(user_id=2)

    # Check that the room stays as is.
    assert room.member_ids == {1, 2}
    assert room.pending_invitee_ids == set()
    assert room.status == "active"


# Test exiting a Chat Room with only one other member (Chat Room becomes inactive)
def test_leaving_two_member_room_makes_it_inactive():
    from app.services.chat_room import ChatRoom

    # Set up an active Chat Room with two members.
    room = ChatRoom(member_ids={1, 2}, status="active")

    # Have member 2 exit the Chat Room.
    room.leave(member_id=2)

    # Check who is left and that the Chat Room is inactive.
    assert room.member_ids == {1}
    assert room.status == "inactive"


# Test what happens to a pending invitation when the Chat Room becomes inactive
def test_inactive_room_clears_pending_invitation():
    from app.services.chat_room import ChatRoom

    # Set up an active Chat Room with two members and one invitee.
    room = ChatRoom(member_ids={1, 2}, pending_invitee_ids={3}, status="active")

    # Have member 2 leave so the Chat Room becomes inactive.
    room.leave(member_id=2)

    assert room.status == "inactive"
    assert room.pending_invitee_ids == set()

    # Check that user 3 can no longer join.
    with pytest.raises(PermissionError):
        room.accept_invitation(user_id=3)
    assert room.member_ids == {1}


# Test exiting a Chat Room with two other members (Chat Room stays active)
def test_leaving_three_member_room_keeps_it_active():
    from app.services.chat_room import ChatRoom

    # Set up an active Chat Room with three members.
    room = ChatRoom(member_ids={1, 2, 3}, status="active")

    # Have member 3 exit the Chat Room.
    room.leave(member_id=3)

    # Check that two members are left and the Chat Room stays active.
    assert room.member_ids == {1, 2}
    assert room.status == "active"
