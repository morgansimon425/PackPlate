"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";
import { useSession } from "@/lib/session";

const LINKS = [
  { href: "/home", label: "Home" },
  { href: "/locations", label: "What’s open" },
  { href: "/menus", label: "Menus" },
  { href: "/compare", label: "Compare Meals" },
  { href: "/group", label: "Eat as a group" },
  { href: "/chat", label: "Group Chat" },
  { href: "/busy", label: "How busy" },
  { href: "/profile", label: "My diet" },
  { href: "/", label: "About" },
];

export function SiteHeader() {
  const pathname = usePathname();
  const [open, setOpen] = useState(false);
  const session = useSession();
  // Nothing while loading or offline, so the link doesn't flicker or lie.
  const account =
    session.status === "signed_in"
      ? { href: "/account", label: session.user.username }
      : session.status === "signed_out"
        ? { href: "/login", label: "Log in" }
        : null;

  return (
    <header className="site-header">
      <div className="site-header-inner">
        <Link href="/home" className="brand" onClick={() => setOpen(false)}>
          Pack<span>Plate</span>
        </Link>

        <button
          type="button"
          className="nav-toggle"
          aria-expanded={open}
          aria-controls="site-nav"
          onClick={() => setOpen((value) => !value)}
        >
          <span aria-hidden="true">☰</span> Menu
        </button>

        <nav
          id="site-nav"
          aria-label="Main"
          className={open ? "nav nav-open" : "nav"}
        >
          {LINKS.map((link) => (
            <Link
              key={link.href}
              href={link.href}
              aria-current={pathname === link.href ? "page" : undefined}
              onClick={() => setOpen(false)}
            >
              {link.label}
            </Link>
          ))}
          {account ? (
            <Link
              href={account.href}
              className="nav-account"
              aria-current={pathname === account.href ? "page" : undefined}
              onClick={() => setOpen(false)}
            >
              {account.label}
            </Link>
          ) : null}
        </nav>
      </div>
    </header>
  );
}
