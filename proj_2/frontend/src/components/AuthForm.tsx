"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";
import { errorMessage } from "@/lib/api";
import { login, register, useSession } from "@/lib/session";
import { StateMessage } from "./StateMessage";

// Same rules as the backend (services/auth.py), checked here first so the
// message shows without a round trip. The server still decides.
const USERNAME = /^[A-Za-z0-9_]{3,30}$/;
const PASSWORD_MIN = 8;

function problem(mode: "login" | "signup", username: string, password: string) {
  if (mode === "login") {
    return username && password ? null : "Enter your username and password.";
  }
  if (!USERNAME.test(username.trim())) {
    return "Usernames are 3–30 characters: letters, numbers, or _.";
  }
  if (password.length < PASSWORD_MIN) {
    return `Passwords need at least ${PASSWORD_MIN} characters.`;
  }
  return null;
}

// The log in and sign up forms, which differ only in wording and endpoint.
export function AuthForm({ mode }: { mode: "login" | "signup" }) {
  const router = useRouter();
  const session = useSession();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  if (session.status === "signed_in") {
    return (
      <StateMessage kind="empty">
        You’re logged in as <strong>{session.user.username}</strong>.{" "}
        <Link href="/account">Go to your account</Link>.
      </StateMessage>
    );
  }

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const invalid = problem(mode, username, password);
    if (invalid) {
      setError(invalid);
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await (mode === "login" ? login : register)(username.trim(), password);
      router.push("/home");
    } catch (failure) {
      setError(errorMessage(failure));
      setBusy(false);
    }
  }

  const signup = mode === "signup";
  return (
    <form className="panel form" onSubmit={onSubmit} noValidate>
      <div className="field">
        <label htmlFor="auth-username">Username</label>
        <input
          id="auth-username"
          className="input"
          autoComplete="username"
          autoCapitalize="none"
          spellCheck={false}
          maxLength={30}
          value={username}
          onChange={(e) => setUsername(e.target.value)}
        />
        {signup ? (
          <p className="help">
            3–30 letters, numbers, or _. Others can find you by it.
          </p>
        ) : null}
      </div>

      <div className="field">
        <label htmlFor="auth-password">Password</label>
        <input
          id="auth-password"
          className="input"
          type="password"
          autoComplete={signup ? "new-password" : "current-password"}
          maxLength={128}
          value={password}
          onChange={(e) => setPassword(e.target.value)}
        />
        {signup ? (
          <p className="help">At least {PASSWORD_MIN} characters.</p>
        ) : null}
      </div>

      {error ? (
        <p className="form-error" role="alert">
          {error}
        </p>
      ) : null}

      <div className="button-row">
        <button type="submit" className="btn" disabled={busy}>
          {signup ? "Create account" : "Log in"}
        </button>
      </div>

      <p className="help">
        {signup ? (
          <>
            Already have an account? <Link href="/login">Log in</Link>.
          </>
        ) : (
          <>
            New here? <Link href="/signup">Create an account</Link>.
          </>
        )}{" "}
        PackPlate stores only your username and a scrambled (hashed) password,
        never your diet.
      </p>
    </form>
  );
}
