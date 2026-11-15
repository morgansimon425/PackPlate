# This file tests using the Chat Room through the API. Milestone 4
#
# What I expect the Chat Room to have:
# - id is how we find the Chat Room and its messages.
# - status tells us if the Chat Room is pending, active, or inactive.
# - member_ids lists the users who HAVE joined the Chat Room.
# When creating a Chat Room, invitee_ids are lists of the people we want to invite.
# Each invitation has its own id and a room_id for the Chat Room it belongs to.
#
# What the User has (from M1, see docs/m1-accounts.md):
# - username is the unique name the user picks, like azalin. This is what I show
#   when the creator searches for someone to invite. Case-insensitive.
# - id is the account's backend ID, like 42 (users.id, an integer).
# - Accounts sign up and log in with username and password.
# - open_to_chat controls whether the user shows up in the Open to Chat list.
# Signing up logs the user in with a session cookie. The tests put each user's
# cookie in headers to make requests as that user.
#
# If the creator picks azalin, look up the account and send 42 in invitee_ids.
# After Alice accepts, add 42 to member_ids. If she changes her username later,
# her account ID stays the same, so she keeps her Chat Rooms.
# Usernames should be unique even with different capitalization.

from datetime import datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.main import app
from app.services.auth import SESSION_COOKIE

CHAT_ROOMS = "/chat/rooms"
CHAT_INVITATIONS = "/chat/invitations"
OPEN_TO_CHAT = "/chat/open-to-chat"


# Create a test User and log them in
@pytest.fixture
def make_chat_user(client):
    def make_user(name):
        credentials = {"username": name, "password": "PackPlate-Test-123!"}
        account = client.post("/auth/register", json=credentials)
        assert account.status_code == 201, account.text

        # Signing up logs in with a cookie. Take it out of the shared client so
        # each user sends only their own cookie, through their headers.
        token = client.cookies[SESSION_COOKIE]
        client.cookies.clear()
        return {
            "id": account.json()["id"],
            "headers": {"Cookie": f"{SESSION_COOKIE}={token}"},
        }

    return make_user


# Create a Chat Room to use
def create_chat_room(client, creator, invitees):
    # Send the account IDs for the usernames the creator picked.
    response = client.post(
        CHAT_ROOMS,
        headers=creator["headers"],
        json={"invitee_ids": [user["id"] for user in invitees]},
    )
    assert response.status_code == 201, response.text
    return response.json()


# Get the invitations sent to this user
def get_invitations(client, user):
    response = client.get(CHAT_INVITATIONS, headers=user["headers"])
    assert response.status_code == 200, response.text
    return response.json()


# Set up an active Chat Room to use in the tests
@pytest.fixture
def active_room(client, make_chat_user):
    # Create a Chat Room and have the other person accept the invitation.
    creator = make_chat_user("alice")
    member = make_chat_user("bob")
    room = create_chat_room(client, creator, [member])
    [invitation] = get_invitations(client, member)
    response = client.post(
        f"{CHAT_INVITATIONS}/{invitation['id']}/accept", headers=member["headers"]
    )
    assert response.status_code == 200, response.text

    # Keep the Chat Room ID and both users so we can make requests as either one.
    return room["id"], creator, member


# Have a member exit the Chat Room
def leave_chat_room(client, room_id, member):
    response = client.post(f"{CHAT_ROOMS}/{room_id}/leave", headers=member["headers"])
    assert response.status_code == 204, response.text


# Room creation and invitations


# Test creating a valid Chat Room with one other person (Chat Room starts pending)
def test_creating_chat_room_with_one_invitee(client, make_chat_user):
    creator = make_chat_user("alice")
    invitee = make_chat_user("bob")

    room = create_chat_room(client, creator, [invitee])

    # Check that only the creator has joined and the other person has an invitation.
    assert room["status"] == "pending"
    assert room["member_ids"] == [creator["id"]]
    [invitation] = get_invitations(client, invitee)
    assert invitation["room_id"] == room["id"]


# Test creating a Chat Room and inviting several people (each gets an invitation)
def test_creating_chat_room_with_several_invitees(client, make_chat_user):
    creator = make_chat_user("alice")
    invitees = [make_chat_user(name) for name in ("bob", "chris", "dan")]

    room = create_chat_room(client, creator, invitees)

    # Check that each person gets an invitation to the same Chat Room.
    assert room["member_ids"] == [creator["id"]]
    for invitee in invitees:
        [invitation] = get_invitations(client, invitee)
        assert invitation["room_id"] == room["id"]


# Test attempting to create a Chat Room without inviting anyone
def test_creating_chat_room_without_invitees(client, make_chat_user):
    creator = make_chat_user("alice")

    response = client.post(
        CHAT_ROOMS, headers=creator["headers"], json={"invitee_ids": []}
    )

    assert response.status_code == 422


# Test inviting the same user twice (no duplicate invitations)
def test_inviting_the_same_user_twice(client, make_chat_user):
    creator = make_chat_user("alice")
    invitee = make_chat_user("bob")

    room = create_chat_room(client, creator, [invitee, invitee])

    # Check that the user only gets one invitation.
    [invitation] = get_invitations(client, invitee)
    assert invitation["room_id"] == room["id"]


# Test attempting to create a Chat Room with an invalid user ID
def test_creating_chat_room_with_unknown_user(client, make_chat_user):
    creator = make_chat_user("alice")
    invitee = make_chat_user("bob")

    response = client.post(
        CHAT_ROOMS,
        headers=creator["headers"],
        json={"invitee_ids": [invitee["id"], 999_999]},
    )
    assert response.status_code == 404

    # Check that the Chat Room and invitations are not created.
    rooms = client.get(CHAT_ROOMS, headers=creator["headers"])
    assert rooms.status_code == 200
    assert rooms.json() == []
    assert get_invitations(client, invitee) == []


# Test attempting to accept or decline another user's Chat Room invitation
@pytest.mark.parametrize("action", ["accept", "decline"])
def test_responding_to_another_users_invitation(client, make_chat_user, action):
    creator = make_chat_user("alice")
    invitee = make_chat_user("bob")
    other_user = make_chat_user("chris")
    create_chat_room(client, creator, [invitee])
    [invitation] = get_invitations(client, invitee)

    response = client.post(
        f"{CHAT_INVITATIONS}/{invitation['id']}/{action}", headers=other_user["headers"]
    )

    assert response.status_code == 403
    assert get_invitations(client, invitee) == [invitation]


# Chat Room access


# Test attempting to create a valid Chat Room while not logged in
def test_creating_chat_room_while_signed_out():
    with TestClient(app) as signed_out_client:
        response = signed_out_client.post(CHAT_ROOMS, json={"invitee_ids": [2]})

    assert response.status_code == 401


# Test attempting to view messages in a Chat Room you have not joined
def test_viewing_messages_as_a_nonmember(client, active_room, make_chat_user):
    room_id, _, _ = active_room
    other_user = make_chat_user("chris")

    response = client.get(
        f"{CHAT_ROOMS}/{room_id}/messages", headers=other_user["headers"]
    )

    assert response.status_code == 403


# Test attempting to send a message in a Chat Room you have not joined
def test_sending_a_message_as_a_nonmember(client, active_room, make_chat_user):
    room_id, _, _ = active_room
    other_user = make_chat_user("lee")

    response = client.post(
        f"{CHAT_ROOMS}/{room_id}/messages",
        headers=other_user["headers"],
        json={"text": "Anyone going to Fountain?"},
    )

    assert response.status_code == 403


# Test attempting to view or send messages after exiting a Chat Room
def test_accessing_messages_after_leaving(client, active_room):
    room_id, _, member = active_room
    leave_chat_room(client, room_id, member)
    messages_url = f"{CHAT_ROOMS}/{room_id}/messages"

    history = client.get(messages_url, headers=member["headers"])
    send = client.post(
        messages_url, headers=member["headers"], json={"text": "Can I still send?"}
    )

    assert history.status_code == 403
    assert send.status_code == 403


# Messages and history


# Test sending and receiving a message in the Chat Room
def test_sending_and_receiving_a_message(client, active_room, db):
    room_id, creator, member = active_room
    messages_url = f"{CHAT_ROOMS}/{room_id}/messages"
    message_text = "Want to meet at Fountain?"

    sent = client.post(
        messages_url, headers=creator["headers"], json={"text": message_text}
    )
    assert sent.status_code == 201

    # Check that the other member can see the message, who sent it, and when.
    # PostgreSQL can return the timestamp in a different time zone than it was sent.
    db.execute(text("SET LOCAL TIME ZONE 'America/New_York'"))
    history = client.get(messages_url, headers=member["headers"])
    assert history.status_code == 200
    [message] = history.json()
    assert message["text"] == message_text
    assert message["sender_id"] == creator["id"]
    assert message["created_at"] == sent.json()["created_at"]
    assert datetime.fromisoformat(message["created_at"]).tzinfo is not None


# Test attempting to send an empty message or a message with only spaces or tabs
@pytest.mark.parametrize("message_text", ["", "   ", "\t\n"])
def test_sending_a_blank_message(client, active_room, message_text):
    room_id, creator, _ = active_room

    response = client.post(
        f"{CHAT_ROOMS}/{room_id}/messages",
        headers=creator["headers"],
        json={"text": message_text},
    )

    assert response.status_code == 422


# Test attempting to send a message as another user
def test_sending_a_message_as_another_user(client, active_room):
    room_id, creator, member = active_room

    response = client.post(
        f"{CHAT_ROOMS}/{room_id}/messages",
        headers=creator["headers"],
        json={"text": "Meet at Fountain?", "sender_id": member["id"]},
    )

    assert response.status_code == 422


# Test attempting to send a message in a pending Chat Room
def test_sending_a_message_in_a_pending_room(client, make_chat_user):
    creator = make_chat_user("alice")
    invitee = make_chat_user("bob")
    room = create_chat_room(client, creator, [invitee])

    response = client.post(
        f"{CHAT_ROOMS}/{room['id']}/messages",
        headers=creator["headers"],
        json={"text": "Is anyone here?"},
    )

    assert response.status_code == 409


# Test attempting to send a message in an inactive Chat Room
def test_sending_a_message_in_an_inactive_room(client, active_room):
    room_id, creator, member = active_room
    leave_chat_room(client, room_id, member)

    response = client.post(
        f"{CHAT_ROOMS}/{room_id}/messages",
        headers=creator["headers"],
        json={"text": "Is anyone still here?"},
    )

    assert response.status_code == 409


# Test viewing an inactive Chat Room (the remaining member can still see messages)
def test_viewing_an_inactive_room(client, active_room):
    room_id, creator, member = active_room
    messages_url = f"{CHAT_ROOMS}/{room_id}/messages"
    message_text = "Meet at Fountain at noon."

    sent = client.post(
        messages_url, headers=member["headers"], json={"text": message_text}
    )
    assert sent.status_code == 201
    leave_chat_room(client, room_id, member)

    # Check that the Chat Room is inactive and the creator can still see the message.
    room = client.get(f"{CHAT_ROOMS}/{room_id}", headers=creator["headers"])
    assert room.status_code == 200
    assert room.json()["status"] == "inactive"
    history = client.get(messages_url, headers=creator["headers"])
    assert history.status_code == 200
    [message] = history.json()
    assert message["text"] == message_text


# Open to Chat


# Test turning on Open to Chat (the user shows up in the list)
def test_turning_on_open_to_chat(client, make_chat_user):
    user = make_chat_user("alice")
    other_user = make_chat_user("bob")

    response = client.put(
        OPEN_TO_CHAT, headers=user["headers"], json={"open_to_chat": True}
    )
    assert response.status_code == 200

    # Check that the other user can see them in the list.
    people = client.get(OPEN_TO_CHAT, headers=other_user["headers"])
    assert people.status_code == 200
    assert [person["id"] for person in people.json()] == [user["id"]]


# Test turning off Open to Chat (the user is removed from the list)
def test_turning_off_open_to_chat(client, make_chat_user):
    user = make_chat_user("alice")
    other_user = make_chat_user("bob")
    response = client.put(
        OPEN_TO_CHAT, headers=user["headers"], json={"open_to_chat": True}
    )
    assert response.status_code == 200
    before = client.get(OPEN_TO_CHAT, headers=other_user["headers"])
    assert before.status_code == 200
    assert [person["id"] for person in before.json()] == [user["id"]]

    response = client.put(
        OPEN_TO_CHAT, headers=user["headers"], json={"open_to_chat": False}
    )
    assert response.status_code == 200

    # Check that the user is removed from the list after turning it off.
    after = client.get(OPEN_TO_CHAT, headers=other_user["headers"])
    assert after.status_code == 200
    assert after.json() == []
