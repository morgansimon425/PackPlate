import { useEffect, useRef, useState, type FormEvent } from "react";
import { StateMessage } from "@/components/StateMessage";
import { errorMessage } from "@/lib/api";
import type { ChatMessage, ChatRoom } from "@/lib/types";

const messageTime = new Intl.DateTimeFormat(undefined, {
  dateStyle: "short",
  timeStyle: "short",
});

// This is where you read messages, reply, or leave the room.
export function ChatConversation({
  room,
  userId,
  usernames,
  messages,
  messageError,
  onRetry,
  onSend,
  onLeave,
}: {
  room: ChatRoom;
  userId: number;
  usernames: Record<number, string>;
  messages?: ChatMessage[];
  messageError?: string;
  onRetry: () => void;
  onSend: (text: string) => Promise<void>;
  onLeave: () => Promise<void>;
}) {
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState<"send" | "leave" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const title = useRef<HTMLHeadingElement>(null);
  const log = useRef<HTMLDivElement>(null);
  const followLatest = useRef(true);
  const latestId = messages?.at(-1)?.id;

  // Move keyboard focus to the room heading when you open it.
  useEffect(() => title.current?.focus(), []);

  // Scroll to new messages while you're near the bottom of the chat.
  useEffect(() => {
    if (log.current && followLatest.current) {
      log.current.scrollTop = log.current.scrollHeight;
    }
  }, [latestId]);

  async function sendMessage(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const text = draft.trim();
    if (!text || busy || room.status !== "active") return;
    setBusy("send");
    setError(null);
    try {
      await onSend(text);
      followLatest.current = true;
      // Keep the draft available until the message goes through.
      setDraft("");
    } catch (failure) {
      setError(errorMessage(failure));
    } finally {
      setBusy(null);
    }
  }

  async function leaveRoom() {
    if (busy) return;
    setBusy("leave");
    setError(null);
    try {
      await onLeave();
    } catch (failure) {
      setError(errorMessage(failure));
    } finally {
      setBusy(null);
    }
  }

  return (
    <section className="panel stack" aria-labelledby="chat-conversation-title">
      <div className="location-row-head">
        <h2
          id="chat-conversation-title"
          className="section-title"
          tabIndex={-1}
          ref={title}
        >
          Room #{room.id}
        </h2>
        <span className="meta">
          {room.member_ids.length}{" "}
          {room.member_ids.length === 1 ? "member" : "members"}
        </span>
      </div>
      {room.status === "pending" ? (
        <p className="help">Waiting for someone to accept an invitation.</p>
      ) : null}
      {room.status === "inactive" ? (
        <p className="help">
          This room is inactive. You can still read past messages.
        </p>
      ) : null}

      {messageError ? (
        <StateMessage kind="error" onRetry={onRetry}>
          {messageError}
        </StateMessage>
      ) : null}
      {messages?.length ? (
        <div
          className="chat-log"
          role="log"
          aria-label="Messages"
          tabIndex={0}
          ref={log}
          onScroll={(event) => {
            const { scrollHeight, scrollTop, clientHeight } =
              event.currentTarget;
            followLatest.current = scrollHeight - scrollTop - clientHeight < 32;
          }}
        >
          <ul className="stack">
            {messages.map((message) => {
              const own = message.sender_id === userId;
              // The API gives us sender IDs. Show the username if we have it.
              const sender =
                message.sender_id === null
                  ? "Deleted user"
                  : own
                    ? "You"
                    : (usernames[message.sender_id] ??
                      `Member #${message.sender_id}`);
              return (
                <li
                  className={
                    own ? "chat-message chat-message-own" : "chat-message"
                  }
                  key={message.id}
                >
                  <div className="chat-message-meta">
                    <strong>{sender}</strong>
                    <time dateTime={message.created_at}>
                      {messageTime.format(new Date(message.created_at))}
                    </time>
                  </div>
                  <p>{message.text}</p>
                </li>
              );
            })}
          </ul>
        </div>
      ) : !messageError && room.status !== "pending" ? (
        <p className="help">
          {messages ? "No messages yet." : "Loading messages…"}
        </p>
      ) : null}

      {room.status === "active" ? (
        <form className="stack" onSubmit={sendMessage}>
          <div className="field">
            <label htmlFor="chat-message">Message</label>
            <textarea
              id="chat-message"
              className="input chat-message-input"
              rows={2}
              value={draft}
              disabled={busy !== null}
              onChange={(event) => setDraft(event.target.value)}
            />
          </div>
          <div className="button-row">
            <button
              className="btn btn-small"
              type="submit"
              disabled={!draft.trim() || busy !== null}
            >
              {busy === "send" ? "Sending…" : "Send"}
            </button>
          </div>
        </form>
      ) : null}
      {error ? (
        <p className="form-error" role="alert">
          {error}
        </p>
      ) : null}
      <div className="button-row">
        <button
          className="btn btn-quiet btn-small"
          type="button"
          disabled={busy !== null}
          onClick={() => void leaveRoom()}
        >
          {busy === "leave" ? "Leaving…" : "Leave room"}
        </button>
      </div>
    </section>
  );
}
