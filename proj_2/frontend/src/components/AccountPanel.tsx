"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";
import { errorMessage } from "@/lib/api";
import {
  deleteAccount,
  logout,
  setOpenToChat,
  useSession,
} from "@/lib/session";
import { StateMessage } from "./StateMessage";

export function AccountPanel() {
  const router = useRouter();
  const session = useSession();
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  if (session.status === "loading")
    return <StateMessage kind="loading">Checking your account…</StateMessage>;
  if (session.status === "unknown")
    return (
      <StateMessage kind="error">
        Can’t reach the PackPlate server right now.
      </StateMessage>
    );
  if (session.status === "signed_out")
    return (
      <StateMessage kind="empty">
        You’re not logged in. <Link href="/login">Log in</Link> or{" "}
        <Link href="/signup">create an account</Link>.
      </StateMessage>
    );

  async function onLogout() {
    setBusy(true);
    try {
      await logout();
      router.push("/home");
    } catch (failure) {
      setError(errorMessage(failure));
      setBusy(false);
    }
  }

  async function onToggleChat(value: boolean) {
    setBusy(true);
    setError(null);
    try {
      await setOpenToChat(value);
    } catch (failure) {
      setError(errorMessage(failure));
    }
    setBusy(false);
  }

  async function onDelete(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await deleteAccount(password);
      router.push("/home");
    } catch (failure) {
      setError(errorMessage(failure));
      setBusy(false);
    }
  }

  return (
    <>
      <section className="panel" aria-labelledby="account-title">
        <h2 id="account-title" className="section-title">
          {session.user.username}
        </h2>
        <p className="help">
          Member since{" "}
          {new Date(session.user.created_at).toLocaleDateString(undefined, {
            dateStyle: "long",
          })}
          . Your dietary profile still lives only in this browser.
        </p>
        <label className="checkbox-line">
          <input
            type="checkbox"
            checked={session.user.open_to_chat}
            disabled={busy}
            onChange={(e) => onToggleChat(e.target.checked)}
          />
          <span>
            <strong>Open to Chat</strong>: list me so other PackPlate users can
            invite me to plan meals. Off by default.
          </span>
        </label>
        <div className="button-row">
          <button
            type="button"
            className="btn"
            onClick={onLogout}
            disabled={busy}
          >
            Log out
          </button>
        </div>
      </section>

      <form
        className="panel form"
        onSubmit={onDelete}
        aria-labelledby="delete-title"
      >
        <h2 id="delete-title" className="section-title">
          Delete my account
        </h2>
        <p className="help">
          This removes your account and everything tied to it from PackPlate’s
          servers. It can’t be undone.
        </p>
        <div className="field">
          <label htmlFor="delete-password">Your password</label>
          <input
            id="delete-password"
            className="input"
            type="password"
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        </div>
        {error ? (
          <p className="form-error" role="alert">
            {error}
          </p>
        ) : null}
        <div className="button-row">
          <button
            type="submit"
            className="btn btn-outline"
            disabled={busy || !password}
          >
            Delete my account
          </button>
        </div>
      </form>
    </>
  );
}
