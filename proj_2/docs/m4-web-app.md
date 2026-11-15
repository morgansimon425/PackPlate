# M4 — "Where can we eat right now?" web app

**Status (2026-10-18):** wireframes merged into `dev` (Savanah). The frontend
helper code (API client, types, diet logic, profile storage) is on
`feature/frontend`; the page and component files there are still empty.

## Goal

One responsive site, for computer and phone, that answers "where can we eat
right now?" in one view instead of about 20 navigations across two sites.
This is what the demo and both videos show.

## Pages (from the wireframes)

| Page | Shows | Backed by |
|---|---|---|
| Home | The five features below | — |
| What's Open Now | Open locations and their hours; closed ones below, with a dropdown for future menus | `GET /locations` |
| Menus & Nutrition | A location's menus for a day, with allergens, diets, and nutrition | `GET /locations/{id}/menus` |
| My Dietary Profile | Allergies and dietary preferences | Used by the two filter endpoints |
| Eat as a Group | Several profiles; locations where everyone can eat | `POST /filters/group` |
| How Busy Is It? | Each location's crowd level, and a way to report | `POST /crowd/{id}`, `crowd` in `GET /locations` |
| Login / Signup | Username and password; an account page to log out or delete it | `/auth/*` (M1, see [m1-accounts.md](m1-accounts.md)) |

## Must get right

- **Show `incomplete` honestly.** An incomplete item is never shown as safe, and
  its reasons are visible ("no nutrition label: allergens come from icons
  only").
- **Show data freshness** from `GET /freshness`, and warn when data is stale.
- **Typed API contract.** Generate TypeScript types from the API's OpenAPI
  spec, so a field renamed on one side breaks the build instead of the demo.
  The architecture critique named frontend/backend field mismatches as a
  likely week-3 failure.
- **NC State theme**, as the wireframes note.

## For the team to decide

The wireframes include Login/Signup and a saved "My Dietary Profile". The
backend currently never stores dietary information, following the 1b
report's privacy stakeholders. Options:

1. No accounts: keep the profile in the browser (local storage) only.
2. Accounts that store profiles, which needs auth, a new table, and a
   privacy note about storing health-related data.

Option 1 delivers the same experience with far less risk and work.

**Decided (2026-11-09, M1):** both. Accounts exist (username and password
only) for features that need to know who you are, like group chat, but the
dietary profile still stays in the browser. See [m1-accounts.md](m1-accounts.md).

## Checklist

- [x] Wireframes for every page
- [x] Frontend helper code: API client, types, diet logic, profile storage
  (on `feature/frontend`)
- [ ] Home page
- [ ] What's Open Now page
- [ ] Menus & Nutrition page
- [ ] My Dietary Profile page
- [ ] Eat as a Group page
- [ ] How Busy Is It? page
- [x] Login decision made: accounts, but profiles stay in the browser (M1)
- [ ] `incomplete` items never shown as safe, with their reasons visible
- [ ] Data freshness shown, with a warning when stale
- [ ] TypeScript types generated from the API, not hand-written (`types.ts`
  is hand-written for now)
- [ ] NC State theme
- [ ] Every page works on a phone and a computer, against the real API
- [ ] A group can go from opening the site to choosing a location in under
  two minutes (measured in M0's bonus study)
- [ ] Teaser (12–30 s) and walk-through (2–5 min) videos recorded from it
