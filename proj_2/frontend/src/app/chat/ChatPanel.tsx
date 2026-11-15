"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { StateMessage } from "@/components/StateMessage";
import { api, ApiError, errorMessage } from "@/lib/api";
import { refreshSession, setOpenToChat, useSession } from "@/lib/session";
import type { ChatPerson, ChatRoom, User } from "@/lib/types";
import { useAsync } from "@/lib/useAsync";
import { ChatConversation } from "./ChatConversation";
import { CreateRoom } from "./CreateRoom";

const REFRESH_MS = 5000;

const STATUS_PILLS = {
  pending: { label: "Pending", className: "pill-warn" },
  active: { label: "Active", className: "pill-ok" },
  inactive: { label: "Inactive", className: "" },
};

// Give each request time to finish before we check for updates again.
function useChatPoll(reload: () => void, loading: boolean, enabled = true) {
  useEffect(() => {
    if (!enabled || loading) return;
    const timer = window.setTimeout(reload, REFRESH_MS);
    return () => window.clearTimeout(timer);
  }, [enabled, loading, reload]);
}

async function withSession<T>(request: Promise<T>): Promise<T> {
  try {
    return await request;
  } catch (error) {
    // Check the shared login state again if the session expired.
    if (error instanceof ApiError && error.status === 401)
      void refreshSession();
    throw error;
  }
}

export function ChatPanel() {
  const session = useSession();
  if (session.status === "loading") {
    return <StateMessage kind="loading">Checking your account…</StateMessage>;
  }
  if (session.status === "unknown") {
    return (
      <StateMessage kind="error" onRetry={() => void refreshSession()}>
        Can’t reach the PackPlate server right now.
      </StateMessage>
    );
  }
  if (session.status === "signed_out") {
    return (
      <StateMessage kind="empty">
        <Link href="/login">Log in</Link> or{" "}
        <Link href="/signup">create an account</Link> to join Group Chat.
      </StateMessage>
    );
  }
  // Start fresh when someone switches accounts so their rooms and drafts stay separate.
  return <ChatWorkspace key={session.user.id} user={session.user} />;
}

function ChatWorkspace({ user }: { user: User }) {
  const [roomId, setRoomId] = useState<number | null>(null);
  const [knownPeople, setKnownPeople] = useState<Record<number, string>>({});
  const [updating, setUpdating] = useState(false);
  const [pendingPreference, setPendingPreference] = useState<boolean | null>(
    null,
  );
  const [actionError, setActionError] = useState<string | null>(null);

  // Load the room list, invites, and Open to Chat list together.
  const board = useAsync(
    async () => {
      const [rooms, invitations, people] = await withSession(
        Promise.all([
          api.chatRooms(),
          api.chatInvitations(),
          api.openToChatPeople(),
        ]),
      );
      return { rooms, invitations, people };
    },
    "chat-board",
    { keepDataOnError: true },
  );
  const selectedRoom = board.data?.rooms.find((room) => room.id === roomId);
  const selectedId = selectedRoom?.id;
  // Only load messages for the room we have open.
  const history = useAsync(
    () =>
      selectedId === undefined
        ? Promise.resolve([])
        : withSession(api.chatMessages(selectedId)),
    `chat-history-${selectedId}`,
  );
  useChatPoll(board.reload, board.loading);
  useChatPoll(history.reload, history.loading, selectedId !== undefined);

  async function updateBoard(action: () => Promise<unknown>) {
    setUpdating(true);
    setActionError(null);
    try {
      await withSession(action());
    } catch (error) {
      setActionError(errorMessage(error));
    } finally {
      board.reload();
      setUpdating(false);
    }
  }

  async function changeDiscovery(checked: boolean) {
    // Show the change while it saves, then use the value from the account.
    setPendingPreference(checked);
    await updateBoard(() => setOpenToChat(checked));
    setPendingPreference(null);
  }

  async function createRoom(invitees: ChatPerson[]) {
    const room = await withSession(
      api.createChatRoom(invitees.map(({ id }) => id)),
    );
    // Remember the invitees' usernames so we can show them in the chat later.
    setKnownPeople((known) => ({
      ...known,
      ...Object.fromEntries(invitees.map(({ id, username }) => [id, username])),
    }));
    setRoomId(room.id);
    board.reload();
  }

  async function sendMessage(room: ChatRoom, text: string) {
    try {
      await withSession(api.sendChatMessage(room.id, text));
      history.reload();
    } catch (error) {
      board.reload();
      throw error;
    }
  }

  async function leaveRoom(room: ChatRoom) {
    await withSession(api.leaveChatRoom(room.id));
    setRoomId((current) => (current === room.id ? null : current));
    board.reload();
  }

  if (!board.data) {
    return board.error ? (
      <StateMessage kind="error" onRetry={board.reload}>
        {board.error}
      </StateMessage>
    ) : (
      <StateMessage kind="loading">Loading your chat rooms…</StateMessage>
    );
  }

  const { rooms, invitations, people } = board.data;

  return (
    <>
      {board.error ? (
        <StateMessage kind="error" onRetry={board.reload}>
          {board.error}
        </StateMessage>
      ) : null}
      {actionError ? (
        <p className="form-error" role="alert">
          {actionError}
        </p>
      ) : null}
      <div className="chat-layout">
        <div className="stack chat-rooms">
          <section className="panel stack" aria-labelledby="chat-rooms-title">
            <h2 id="chat-rooms-title" className="section-title">
              Your chat rooms
            </h2>
            {rooms.length ? (
              <ul className="stack">
                {rooms.map((room) => {
                  const status = STATUS_PILLS[room.status];
                  return (
                    <li key={room.id}>
                      <button
                        className="btn btn-quiet btn-small chat-room-button"
                        type="button"
                        aria-pressed={room.id === roomId}
                        onClick={() => setRoomId(room.id)}
                      >
                        Room #{room.id}
                        <span className={`pill ${status.className}`}>
                          {status.label}
                        </span>
                      </button>
                    </li>
                  );
                })}
              </ul>
            ) : (
              <p className="help">
                Create a room or accept an invitation to start chatting.
              </p>
            )}
          </section>

          <section
            className="panel stack"
            aria-labelledby="chat-invitations-title"
          >
            <h2 id="chat-invitations-title" className="section-title">
              Pending invitations
            </h2>
            {invitations.length ? (
              <ul className="stack">
                {invitations.map((invitation) => (
                  <li key={invitation.id} className="stack">
                    <span>You’re invited to room #{invitation.room_id}.</span>
                    <div className="button-row">
                      <button
                        className="btn btn-small"
                        type="button"
                        disabled={updating}
                        aria-label={`Accept invitation to room ${invitation.room_id}`}
                        onClick={() =>
                          void updateBoard(async () => {
                            const room = await api.acceptChatInvitation(
                              invitation.id,
                            );
                            setRoomId(room.id);
                          })
                        }
                      >
                        Accept
                      </button>
                      <button
                        className="btn btn-quiet btn-small"
                        type="button"
                        disabled={updating}
                        aria-label={`Decline invitation to room ${invitation.room_id}`}
                        onClick={() =>
                          void updateBoard(() =>
                            api.declineChatInvitation(invitation.id),
                          )
                        }
                      >
                        Decline
                      </button>
                    </div>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="help">You don’t have any pending invitations.</p>
            )}
          </section>
        </div>

        <div className="chat-conversation">
          {selectedRoom ? (
            <ChatConversation
              key={selectedRoom.id}
              room={selectedRoom}
              userId={user.id}
              usernames={{
                ...Object.fromEntries(
                  people.map(({ id, username }) => [id, username]),
                ),
                ...knownPeople,
              }}
              messages={history.data}
              messageError={history.error}
              onRetry={history.reload}
              onSend={(text) => sendMessage(selectedRoom, text)}
              onLeave={() => leaveRoom(selectedRoom)}
            />
          ) : (
            <section
              className="panel stack"
              aria-labelledby="chat-conversation-title"
            >
              <h2 id="chat-conversation-title" className="section-title">
                Conversation
              </h2>
              <p className="help">Select a room to read its messages.</p>
            </section>
          )}
        </div>

        <div className="stack chat-setup">
          <CreateRoom
            people={people}
            onLookup={(username) => withSession(api.chatPerson(username))}
            onCreate={createRoom}
          />

          <section className="panel stack" aria-labelledby="open-to-chat-title">
            <h2 id="open-to-chat-title" className="section-title">
              Open to Chat
            </h2>
            <label className="checkbox-line">
              <input
                type="checkbox"
                checked={pendingPreference ?? user.open_to_chat}
                disabled={updating}
                onChange={(event) => void changeDiscovery(event.target.checked)}
              />
              Show me on the Open to Chat list
            </label>
            <p className="help">
              People who know your exact username can still invite you.
            </p>
          </section>
        </div>
      </div>
    </>
  );
}
