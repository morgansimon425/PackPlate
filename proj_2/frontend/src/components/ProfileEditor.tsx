"use client";

import Link from "next/link";
import { useState, type FormEvent } from "react";
import { emptyProfile, validateProfile } from "@/lib/diet";
import {
  clearProfile,
  saveProfile,
  useHydrated,
  useSavedProfile,
} from "@/lib/profileStore";
import type { Profile } from "@/lib/types";
import { ProfileFields } from "./ProfileFields";
import { StateMessage } from "./StateMessage";

type Status = "idle" | "saved" | "cleared" | "blocked";

function ProfileForm({ initial }: { initial: Profile }) {
  const [draft, setDraft] = useState<Profile>(initial);
  const [status, setStatus] = useState<Status>("idle");
  const [problem, setProblem] = useState<string | null>(null);

  function update(next: Profile) {
    setDraft(next);
    setStatus("idle");
    setProblem(null);
  }

  function onSave(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const invalid = validateProfile(draft);
    if (invalid) {
      setProblem(invalid);
      return;
    }
    const stored = saveProfile({ ...draft, name: draft.name?.trim() ?? "" });
    setStatus(stored ? "saved" : "blocked");
  }

  function onClear() {
    clearProfile();
    setDraft(emptyProfile());
    setProblem(null);
    setStatus("cleared");
  }

  return (
    <>
      <form className="panel form" onSubmit={onSave}>
        <ProfileFields idPrefix="me" value={draft} onChange={update} showName />

        {problem ? (
          <p className="form-error" role="alert">
            {problem}
          </p>
        ) : null}

        <div className="button-row">
          <button type="submit" className="btn">
            Save my profile
          </button>
          <button type="button" className="btn btn-quiet" onClick={onClear}>
            Clear profile
          </button>
        </div>

        {status === "saved" ? (
          <p className="banner banner-ok" role="status">
            Saved.{" "}
            <Link href="/menus" style={{ fontWeight: 700 }}>
              See menus for you
            </Link>
            {" or "}
            <Link href="/group" style={{ fontWeight: 700 }}>
              eat as a group
            </Link>
            .
          </p>
        ) : null}
        {status === "cleared" ? (
          <p className="banner" role="status">
            Your profile was cleared from this browser.
          </p>
        ) : null}
        {status === "blocked" ? (
          <p className="banner banner-bad" role="alert">
            Your browser wouldn’t let PackPlate save this (private browsing can
            do that). You can still use it on the Group page for this visit.
          </p>
        ) : null}
      </form>

      <section className="panel" aria-labelledby="privacy-title">
        <h2 id="privacy-title" className="section-title">
          Where is this kept?
        </h2>
        <p className="help">
          Only in this browser on this device, even if you have an account.
          PackPlate doesn’t store your diet on its servers. It’s sent along when
          you check a menu so the check can be done, and then it’s forgotten.
        </p>
      </section>
    </>
  );
}

export function ProfileEditor() {
  const hydrated = useHydrated();
  const saved = useSavedProfile();

  // Wait for the browser so the form starts from what is actually saved.
  if (!hydrated)
    return <StateMessage kind="loading">Loading your profile…</StateMessage>;
  return <ProfileForm initial={saved} />;
}
