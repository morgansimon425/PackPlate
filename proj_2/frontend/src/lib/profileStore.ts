"use client";

// The dietary profile lives in this browser only (localStorage), even for
// logged-in users: accounts store a username and password hash, nothing else.
// The profile is sent to the API in a request body when you filter a menu, and
// the server never stores it.
import { useMemo, useSyncExternalStore } from "react";
import { parseProfile } from "./diet";
import type { Profile } from "./types";

const STORAGE_KEY = "packplate.profile.v1";
const listeners = new Set<() => void>();

function read(): string | null {
  try {
    return window.localStorage.getItem(STORAGE_KEY);
  } catch {
    return null; // storage blocked (private mode, etc.)
  }
}

function subscribe(onChange: () => void): () => void {
  listeners.add(onChange);
  window.addEventListener("storage", onChange);
  return () => {
    listeners.delete(onChange);
    window.removeEventListener("storage", onChange);
  };
}

function notify() {
  listeners.forEach((listener) => listener());
}

// Returns false if the browser refused to store it.
export function saveProfile(profile: Profile): boolean {
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(profile));
  } catch {
    return false;
  }
  notify();
  return true;
}

export function clearProfile(): void {
  try {
    window.localStorage.removeItem(STORAGE_KEY);
  } catch {
    // nothing stored, nothing to clear
  }
  notify();
}

// true once running in the browser. Forms that start from the saved profile
// wait for this so they never initialise from the empty server-side value.
export function useHydrated(): boolean {
  return useSyncExternalStore(
    () => () => {},
    () => true,
    () => false,
  );
}

export function useSavedProfile(): Profile {
  const raw = useSyncExternalStore(subscribe, read, () => null);
  return useMemo(() => parseProfile(raw), [raw]);
}
