# Security — Tilal Mall shop editor

A plain-language summary of who can do what, and the checks to keep it locked.

## What is public on purpose
- **Reading shop info** (names, descriptions, photos) — it's a public mall
  directory, so anyone can read it. This is intended.
- The **`sb_publishable_…` key** in the website. It is meant to be public. By
  itself it can only *read* public data; it cannot edit anything or read users.

## What is protected
- **Editing** any shop requires logging in. The public/anon key cannot write —
  enforced by database Row-Level Security, not by website code, so it can't be
  bypassed.
- **User accounts & emails are NOT exposed.** The `auth.users` table is not
  reachable through the public API, and the `profiles` table is readable only by
  the user themselves (or an admin). A stranger querying it gets nothing.
- **The `service_role` (master) key** is never in the website or the repo — only
  used locally for the one-time data load.

## ⚠️ The one setting you must keep correct
Because "any logged-in user can edit", the lock on the front door is **disabled
sign-up**. If public sign-up is ON, a stranger could register and then edit.

**Check it:** Supabase dashboard → **Authentication → Sign In / Providers**
(or **Providers → Email**) → make sure **"Allow new users to sign up"** is
**OFF**. Only users you create under **Authentication → Users** should be able to
log in.

> Want belt-and-suspenders? Run `backend/harden_security.sql` — then even a
> stranger who somehow registered would be a powerless "viewer".

## Recommended dashboard settings
- **Authentication → Providers → Email:** disable sign-ups (above); keep email
  confirmation on.
- **Authentication → Policies / Password:** enable **leaked-password
  protection**; require a reasonable minimum length.
- **Authentication → Rate limits:** leave the defaults on (they throttle
  password-guessing).
- Give each editor their **own** account (don't share one login), so you can
  remove one person without changing everyone's password.

## How to verify nobody can read your users
Open these in a browser — both should return an empty list `[]` or an error,
never real user data:

    https://skxbeixiplhmqqeqqube.supabase.co/rest/v1/profiles?apikey=YOUR_PUBLISHABLE_KEY&select=*
    https://skxbeixiplhmqqeqqube.supabase.co/rest/v1/users?apikey=YOUR_PUBLISHABLE_KEY&select=*

`profiles` should come back as `[]` (blocked by row-level security) and `users`
should be "not found" (the auth table isn't exposed at all).

## If a key is ever leaked
- The **publishable key** leaking is harmless (it's public anyway).
- If the **service_role** key ever leaks: Supabase → **Project Settings → API →
  Roll/Reset** the key immediately, and never put it in the browser or git.
