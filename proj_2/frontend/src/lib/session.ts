"use client";

// Who is logged in, shared by every component (the header, the login pages,
// and any feature that needs an account, like chat). The server holds the
// session in an HttpOnly cookie; this only caches GET /auth/me so the header
// doesn't refetch on every page.
//
//   const session = useSession();
//   if (session.status === "signed_in") session.user.username
import { useSyncExternalStore } from "react";
import { api, ApiError } from "./api";
import type { User } from "./types";

export type Session =
  | { status: "loading" }
  | { status: "signed_out" }
  | { status: "signed_in"; user: User }
  | { status: "unknown" }; // the server couldn't be reached

const LOADING: Session = { status: "loading" };
let current: Session = LOADING;
let revision = 0;
let sessionChannel: BroadcastChannel | undefined;
const listeners = new Set<() => void>();

function set(next: Session) {
  revision += 1;
  current = next;
  listeners.forEach((listener) => listener());
}

export async function refreshSession(): Promise<Session> {
  const requestRevision = ++revision;
  let next: Session;
  try {
    next = { status: "signed_in", user: await api.me() };
  } catch (error) {
    const reachable = error instanceof ApiError && error.status === 401;
    next = reachable ? { status: "signed_out" } : { status: "unknown" };
  }
  // A slower refresh must not restore an account after its session changes.
  if (requestRevision === revision) set(next);
  return current;
}

function subscribe(onChange: () => void): () => void {
  const first = listeners.size === 0;
  listeners.add(onChange);
  if (first) {
    if (typeof BroadcastChannel === "function") {
      sessionChannel = new BroadcastChannel("packplate-session");
      sessionChannel.onmessage = ({ data }) => {
        // Tabs share the session cookie, so clear the old account's view first.
        if (data === "identity") set(LOADING);
        if (data === "identity" || data === "preferences")
          void refreshSession();
      };
    }
    void refreshSession();
  }
  return () => {
    listeners.delete(onChange);
    if (listeners.size === 0) {
      sessionChannel?.close();
      sessionChannel = undefined;
    }
  };
}

export function useSession(): Session {
  return useSyncExternalStore(
    subscribe,
    () => current,
    () => LOADING,
  );
}

function setIdentity(next: Session) {
  set(next);
  sessionChannel?.postMessage("identity");
}

export async function register(username: string, password: string) {
  setIdentity({
    status: "signed_in",
    user: await api.register(username, password),
  });
}

export async function login(username: string, password: string) {
  setIdentity({
    status: "signed_in",
    user: await api.login(username, password),
  });
}

export async function logout() {
  await api.logout();
  setIdentity({ status: "signed_out" });
}

export async function setOpenToChat(value: boolean) {
  const user = await api.setOpenToChat(value);
  if (current.status === "signed_in" && current.user.id === user.id) {
    set({ status: "signed_in", user });
  }
  sessionChannel?.postMessage("preferences");
}

export async function deleteAccount(password: string) {
  await api.deleteAccount(password);
  setIdentity({ status: "signed_out" });
}
