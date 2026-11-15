# M1 — User accounts

**Status (2026-11-09):** done on `M1User-accounts`: backend, migration,
frontend pages, and tests. M4's chat backend (Abigail's
`Abigail/M4_implementation`) is merged into the same branch and connected to
accounts; see "M4 chat, connected" below. Not merged to `dev` yet.

## Goal

Let students sign up, log in, and log out, so features that need to know who
someone is (M4 group chat, M5 food preferences, maybe M3's chatbot) have
accounts to build on.

## What an account is

| Stored | Not stored |
|---|---|
| username (3–30 of `a-z 0-9 _`, case-insensitive, unique) | email, real name, student ID |
| scrypt hash of the password (salted, never the password) | the dietary profile (still in the browser only) |
| Open to Chat (off by default) | anything about crowd reports |
| when the account was made | |

Fewer fields means less to protect. The 1b report's privacy stakeholders are
why the diet stays in the browser.

## How sign-in works

- `POST /auth/register` or `/auth/login` sets a `packplate_session` cookie:
  a random 256-bit token, **HttpOnly** (page scripts, and so XSS, can't read
  it), **SameSite=Lax** (not sent on cross-site POSTs, so no CSRF), and
  **Secure** when `COOKIE_SECURE=1`.
- The database stores only the token's SHA-256 in `auth_sessions`. Logging out
  deletes the row, so the cookie is dead even if someone copied it. Sessions
  last `SESSION_DAYS` (30).
- Wrong username and wrong password give the same 401 and take the same time,
  so the login form doesn't reveal who has an account. After 10 failures for
  one username from one client in 15 minutes, logins are refused (429).
- Passwords use `hashlib.scrypt` from the standard library: no new
  dependency. The cost is stored in each hash and old hashes are upgraded on
  login if it's raised.
- Deleting an account needs the password, and deletes everything tied to it
  (`ON DELETE CASCADE`).

Everything that worked logged out still works logged out.

## Building on accounts (M4, M5, M3)

**Backend.** Require a login with one dependency:

```python
from app.deps import current_user, optional_user
from db.models import User

@router.get("/chat/rooms")
def my_rooms(user: User = Depends(current_user), db: Session = Depends(get_db)):
    ...  # 401 is automatic when logged out; user.id, user.username

@router.get("/something")
def either(user: User | None = Depends(optional_user)):
    ...  # None when logged out
```

**Database.** Your migration goes after this one: `down_revision = "0005"`
(and renumber if two features land at once: Alembic needs one head). Reference
`users.id` with `ondelete="CASCADE"` so account deletion cleans up, or
`SET NULL` for records other people still need (like chat messages). If your
feature's rows need cleanup rules beyond a cascade, call them from
`delete_me` in `api/auth.py` before the user is deleted, as chat does.

### M4 chat, connected

| Need | Provided by |
|---|---|

| A unique account ID for members, invites, and senders | `users.id` (`user.id` from `current_user`) |
| A unique username to find people and invite them | `users.username`, unique and lowercased |
| Open to Chat, off by default | `users.open_to_chat`. Chat's `PUT /chat/open-to-chat` and the `/account` checkbox (`PATCH /auth/me`) both set it; `GET /chat/open-to-chat` lists everyone else who has it on |
| Who is asking | every `/chat` route takes `current_user`; the sender of a message is always the logged-in user |

- Chat's tables (`db/chat_models.py`, migration `0006`) reference `users.id`.
  Memberships and invitations cascade; `chat_messages.sender_id` is
  `SET NULL`, so a deleted user's messages stay for the others as
  `sender_id: null`.
- Deleting an account first leaves each of its rooms through chat's normal
  rules (`chat_rooms.leave_all_rooms`). A plain cascade would leave an
  "active" room with one member, which the rules refuse to load, or a pending
  room with no creator.
- Open to Chat controls whether an account appears in the discovery list.
  A signed-in user who knows someone's exact username can still look them up
  and invite them by ID.

**Username lookup.** `GET /chat/users/{username}` returns the other account's
`id` and `username`. Use the ID in `POST /chat/rooms`. Usernames are
case-insensitive.

**Tests.** `client` in `backend/tests/conftest.py` keeps cookies between calls,
so register and you're logged in:

```python
client.post("/auth/register", json={"username": "alice", "password": "password1"})
client.get("/chat/rooms")  # as alice
```

For a second user, make a second `TestClient(app)` (same overrides apply).

**Frontend.** All `api.ts` calls already send the cookie
(`credentials: "include"`); add your calls to `api` or use the same
`request` pattern in your own file. For who's logged in:

```tsx
import { useSession } from "@/lib/session";
const session = useSession(); // "loading" | "signed_in" | "signed_out" | "unknown"
if (session.status === "signed_in") session.user.username;
```

Send logged-out users to `/login`.

## Deploying

- The frontend and API must be **same-site** for the cookie: `localhost:3000`
  with `localhost:8000` works; `localhost` with `127.0.0.1` doesn't. In
  production, serve them from one domain (e.g. `packplate.app` and
  `api.packplate.app`), with `FRONTEND_ORIGIN` set to the frontend's exact
  origin and `COOKIE_SECURE=1`.
- The login limiter is in memory, like the crowd throttle: fine for one API
  process, resets on restart.

## Not done (on purpose)

- Password reset: there's no email to send a link to. A user who forgets
  their password makes a new account.
- Changing username or password.
- Moving the dietary profile into the account (that's M5's call).

## Checklist

- [x] Account requirements and design (this doc)
- [x] `users` and `auth_sessions` tables, migration 0005
- [x] Register, login, logout, who-am-I, delete account
- [x] Open to Chat setting (off by default) for M4
- [x] `current_user` / `optional_user` for other features
- [x] Login, signup, and account pages; header shows Log in or your username
- [x] Tests: hashing, rules, limiter (unit); every route and the cookie (API)
- [ ] Tried in a browser by a teammate against the shared database
