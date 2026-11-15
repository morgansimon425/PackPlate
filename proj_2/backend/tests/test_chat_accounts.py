"""How Chat Rooms (M4) and accounts (M1) fit together, against the test database."""

from sqlalchemy import select

from app.services.auth import SESSION_COOKIE
from db.chat_models import ChatInvitation, ChatMessage, ChatRoomMember

PASSWORD = "PackPlate-Test-123!"


def make_user(client, name):
    account = client.post(
        "/auth/register", json={"username": name, "password": PASSWORD}
    )
    assert account.status_code == 201, account.text
    token = client.cookies[SESSION_COOKIE]
    client.cookies.clear()
    return {
        "id": account.json()["id"],
        "headers": {"Cookie": f"{SESSION_COOKIE}={token}"},
    }


def active_room(client):
    alice, bob = make_user(client, "alice"), make_user(client, "bob")
    room = client.post(
        "/chat/rooms", headers=alice["headers"], json={"invitee_ids": [bob["id"]]}
    ).json()
    [invitation] = client.get("/chat/invitations", headers=bob["headers"]).json()
    client.post(f"/chat/invitations/{invitation['id']}/accept", headers=bob["headers"])
    return room["id"], alice, bob


def test_deleting_an_account_keeps_its_messages_for_others(client, db):
    room_id, alice, bob = active_room(client)
    messages = f"/chat/rooms/{room_id}/messages"
    client.post(messages, headers=bob["headers"], json={"text": "Fountain at 6?"})

    deleted = client.request(
        "DELETE", "/auth/me", headers=bob["headers"], json={"password": PASSWORD}
    )
    assert deleted.status_code == 204

    # Bob's membership is gone; his message stays, from a deleted user.
    assert [m.user_id for m in db.scalars(select(ChatRoomMember))] == [alice["id"]]
    history = client.get(messages, headers=alice["headers"])
    assert history.status_code == 200, history.text
    [message] = history.json()
    assert (message["text"], message["sender_id"]) == ("Fountain at 6?", None)


def test_deleting_an_account_removes_its_invitations(client, db):
    alice, bob = make_user(client, "alice"), make_user(client, "bob")
    client.post(
        "/chat/rooms", headers=alice["headers"], json={"invitee_ids": [bob["id"]]}
    )
    client.request(
        "DELETE", "/auth/me", headers=bob["headers"], json={"password": PASSWORD}
    )
    assert db.scalars(select(ChatInvitation)).all() == []


def test_sender_comes_from_the_login(client, db):
    room_id, alice, _ = active_room(client)
    client.post(
        f"/chat/rooms/{room_id}/messages", headers=alice["headers"], json={"text": "hi"}
    )
    assert db.scalars(select(ChatMessage)).one().sender_id == alice["id"]


def test_inviting_yourself(client):
    alice, bob = make_user(client, "alice"), make_user(client, "bob")
    response = client.post(
        "/chat/rooms",
        headers=alice["headers"],
        json={"invitee_ids": [bob["id"], alice["id"]]},
    )
    assert response.status_code == 400
    assert client.get("/chat/rooms", headers=alice["headers"]).json() == []


def test_every_chat_route_needs_a_login(client):
    for method, path in [
        ("GET", "/chat/rooms"),
        ("GET", "/chat/rooms/1"),
        ("POST", "/chat/rooms/1/leave"),
        ("GET", "/chat/invitations"),
        ("POST", "/chat/invitations/1/accept"),
        ("POST", "/chat/invitations/1/decline"),
        ("GET", "/chat/rooms/1/messages"),
        ("GET", "/chat/users/bob"),
        ("GET", "/chat/open-to-chat"),
    ]:
        assert client.request(method, path).status_code == 401, path


def test_inviting_an_account_found_by_username(client):
    alice, bob = make_user(client, "alice"), make_user(client, "bobby")
    headers = alice["headers"]
    assert client.get("/chat/open-to-chat", headers=headers).json() == []

    response = client.get("/chat/users/BoBbY", headers=headers)
    assert response.status_code == 200, response.text
    assert response.json() == {"id": bob["id"], "username": "bobby"}

    room = client.post(
        "/chat/rooms", headers=headers, json={"invitee_ids": [response.json()["id"]]}
    )
    assert room.status_code == 201, room.text
    [invitation] = client.get("/chat/invitations", headers=bob["headers"]).json()
    assert invitation["room_id"] == room.json()["id"]


def test_username_lookup_rejects_partial_matches_and_self(client):
    alice = make_user(client, "alice")
    make_user(client, "bobby")
    headers = alice["headers"]
    assert client.get("/chat/users/bob", headers=headers).status_code == 404
    assert client.get("/chat/users/alice", headers=headers).status_code == 404
    assert client.get("/chat/users/invalid!", headers=headers).status_code == 400


def test_open_to_chat_is_off_by_default_and_hides_yourself(client):
    alice, bob = make_user(client, "alice"), make_user(client, "bob")
    assert client.get("/chat/open-to-chat", headers=bob["headers"]).json() == []

    client.put(
        "/chat/open-to-chat", headers=alice["headers"], json={"open_to_chat": True}
    )
    client.put(
        "/chat/open-to-chat", headers=bob["headers"], json={"open_to_chat": True}
    )
    # Each sees the other, not themselves, by username.
    assert client.get("/chat/open-to-chat", headers=alice["headers"]).json() == [
        {"id": bob["id"], "username": "bob"}
    ]


def test_open_to_chat_matches_the_account_page(client):
    """PUT /chat/open-to-chat and the /account checkbox (PATCH /auth/me) are one setting."""
    alice = make_user(client, "alice")
    client.put(
        "/chat/open-to-chat", headers=alice["headers"], json={"open_to_chat": True}
    )
    assert (
        client.get("/auth/me", headers=alice["headers"]).json()["open_to_chat"] is True
    )
    client.patch("/auth/me", headers=alice["headers"], json={"open_to_chat": False})
    bob = make_user(client, "bob")
    assert client.get("/chat/open-to-chat", headers=bob["headers"]).json() == []


def test_deleting_a_member_closes_the_room_for_the_rest(client):
    room_id, alice, bob = active_room(client)
    client.request(
        "DELETE", "/auth/me", headers=bob["headers"], json={"password": PASSWORD}
    )
    # As if Bob had left: Alice's room is inactive, readable, and read-only.
    room = client.get(f"/chat/rooms/{room_id}", headers=alice["headers"])
    assert room.status_code == 200, room.text
    assert room.json() == {
        "id": room_id,
        "status": "inactive",
        "member_ids": [alice["id"]],
    }
    sent = client.post(
        f"/chat/rooms/{room_id}/messages", headers=alice["headers"], json={"text": "?"}
    )
    assert sent.status_code == 409


def test_deleting_a_creator_cancels_their_pending_invitations(client):
    alice, bob = make_user(client, "alice"), make_user(client, "bob")
    client.post(
        "/chat/rooms", headers=alice["headers"], json={"invitee_ids": [bob["id"]]}
    )
    client.request(
        "DELETE", "/auth/me", headers=alice["headers"], json={"password": PASSWORD}
    )
    # Bob isn't left holding an invitation to a room with nobody in it.
    assert client.get("/chat/invitations", headers=bob["headers"]).json() == []
