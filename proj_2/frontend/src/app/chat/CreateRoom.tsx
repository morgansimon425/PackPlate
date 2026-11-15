import { useState, type FormEvent } from "react";
import { errorMessage } from "@/lib/api";
import type { ChatPerson } from "@/lib/types";

// Pick people from the Open to Chat list or look them up by username.
export function CreateRoom({
  people,
  onLookup,
  onCreate,
}: {
  people: ChatPerson[];
  onLookup: (username: string) => Promise<ChatPerson>;
  onCreate: (invitees: ChatPerson[]) => Promise<void>;
}) {
  const [invitees, setInvitees] = useState<ChatPerson[]>([]);
  const [directorySelection, setDirectorySelection] = useState("");
  const [username, setUsername] = useState("");
  const [busy, setBusy] = useState<"lookup" | "create" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const trimmed = username.trim();
  const alreadyAdded = invitees.some(
    (person) => person.username === trimmed.toLowerCase(),
  );
  const availablePeople = people.filter(
    (person) => !invitees.some(({ id }) => id === person.id),
  );
  const selectedPerson = availablePeople.find(
    ({ id }) => String(id) === directorySelection,
  );

  function addInvitee(person: ChatPerson) {
    // Both ways of adding people check the account ID so each person gets one invite.
    setInvitees((current) =>
      current.some(({ id }) => id === person.id)
        ? current
        : [...current, person],
    );
    setError(null);
  }

  async function findPerson(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!trimmed || alreadyAdded || busy) return;
    setBusy("lookup");
    setError(null);
    try {
      addInvitee(await onLookup(trimmed));
      setUsername("");
    } catch (failure) {
      setError(errorMessage(failure));
    } finally {
      setBusy(null);
    }
  }

  async function createRoom() {
    if (!invitees.length || busy) return;
    setBusy("create");
    setError(null);
    try {
      // Keep your picks until the room is created so you can try again if it fails.
      await onCreate(invitees);
      setInvitees([]);
      setUsername("");
    } catch (failure) {
      setError(errorMessage(failure));
    } finally {
      setBusy(null);
    }
  }

  // Hiding this panel keeps what you've picked so far.
  return (
    <details className="panel chat-create" open>
      <summary className="location-name">Create a room</summary>
      <div className="stack">
        <div className="field">
          <label htmlFor="open-to-chat-user">People open to chat</label>
          <div className="chat-directory">
            <select
              id="open-to-chat-user"
              className="input"
              value={selectedPerson?.id ?? ""}
              disabled={busy !== null || !availablePeople.length}
              onChange={(event) => setDirectorySelection(event.target.value)}
            >
              <option value="">
                {availablePeople.length
                  ? "Choose a username"
                  : people.length
                    ? "All added"
                    : "No one is open to chat"}
              </option>
              {availablePeople.map((person) => (
                <option key={person.id} value={person.id}>
                  {person.username}
                </option>
              ))}
            </select>
            <button
              className="btn btn-outline btn-small"
              type="button"
              disabled={!selectedPerson || busy !== null}
              onClick={() => {
                if (!selectedPerson) return;
                addInvitee(selectedPerson);
                setDirectorySelection("");
              }}
            >
              Add
            </button>
          </div>
        </div>

        <form className="stack" onSubmit={findPerson}>
          <div className="field">
            <label htmlFor="invite-username">Add by exact username</label>
            <input
              id="invite-username"
              className="input"
              value={username}
              onChange={(event) => setUsername(event.target.value)}
              autoComplete="off"
              autoCapitalize="none"
              spellCheck={false}
              maxLength={30}
              disabled={busy !== null}
            />
          </div>
          <div className="button-row">
            <button
              className="btn btn-outline btn-small"
              type="submit"
              disabled={!trimmed || alreadyAdded || busy !== null}
            >
              {busy === "lookup" ? "Looking up…" : "Add username"}
            </button>
          </div>
        </form>

        {invitees.length ? (
          <ul className="stack" aria-label="Selected invitees">
            {invitees.map((person) => (
              <li className="location-row-head" key={person.id}>
                <span>{person.username}</span>
                <button
                  className="btn btn-quiet btn-small"
                  type="button"
                  aria-label={`Remove ${person.username}`}
                  disabled={busy !== null}
                  onClick={() =>
                    setInvitees((current) =>
                      current.filter(({ id }) => id !== person.id),
                    )
                  }
                >
                  Remove
                </button>
              </li>
            ))}
          </ul>
        ) : (
          <p className="help">Add at least one person to create a room.</p>
        )}
        {error ? (
          <p className="form-error" role="alert">
            {error}
          </p>
        ) : null}
        <div className="button-row">
          <button
            className="btn"
            type="button"
            disabled={!invitees.length || busy !== null}
            onClick={() => void createRoom()}
          >
            {busy === "create" ? "Creating room…" : "Create room"}
          </button>
        </div>
      </div>
    </details>
  );
}
