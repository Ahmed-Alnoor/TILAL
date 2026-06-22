# Tilal Mall — Shop Editor Backend (Supabase)

This folder sets up the backend that lets up to ~10 editors change shop names,
descriptions, categories, areas, logos, photos and icons — securely, with login.

The public map stays a static site (GitHub Pages now, the mall's own domain
later). Only the *editing brain* lives in Supabase, so migrating the website
later needs **no data move** — you just add the new domain to Supabase's allowed
list.

## One-time setup (≈15 minutes)

### 1. Create the project
- Go to <https://supabase.com> → **New project** (free tier is fine).
- Save two values from **Project Settings → API**:
  - **Project URL** — e.g. `https://abcd1234.supabase.co`  *(safe to share)*
  - **anon public key** — *(safe to put in the website)*
  - **service_role key** — ⚠️ secret, used only in step 3, **never commit it**.

### 2. Create the database + security rules
- Open **SQL Editor → New query**, paste all of [`schema.sql`](./schema.sql), **Run**.
- This creates the `shops`, `categories`, `profiles` tables, the public-read /
  editor-write security rules, and the `logos` / `photos` / `icons` storage
  buckets.

### 3. Load the existing 1,144 shops
- Back in **SQL Editor → New query**, paste all of
  [`seed_shops.sql`](./seed_shops.sql), **Run**.
- That's it — no code or command line needed. Re-running is safe (it skips
  shops that already exist, so it never overwrites edits).

> *Advanced/optional:* `seed_shops.py` does the same thing from the command
> line if you prefer. Most people should just use the SQL file above.

### 4. Add your editors
- **Authentication → Users → Add user** for each of your ≤10 people
  (email + password). They each automatically get an *editor* profile.
- To make someone an admin (can manage users/categories): in **Table editor →
  profiles**, set their `role` to `admin`.
- Public sign-up is off by default, so **only people you add can log in**.

### 5. Allow your website's domain
- **Authentication → URL Configuration** → add your site URL(s) to *Site URL*
  and *Redirect URLs* — e.g. `https://ahmed-alnoor.github.io` now, and the
  mall's domain later.
- That's the only change needed when the website later moves hosts.

## Then hand back two values
Give me the **Project URL** and the **anon public key**. I'll wire:
- the **map** to read live shop data from Supabase (with the existing
  localStorage cache + offline fallback to baked defaults), and
- the **admin panel** (`admin.html`) — login + searchable shop list + edit form
  with image upload.

## Security, in one line
The website only ever carries the *anon* key, which can do **nothing** except
what the Row-Level-Security rules in `schema.sql` permit: anyone may *read* the
directory, but only a logged-in editor you added may *write*. No password or
role check ever lives in the page's JavaScript, so it can't be bypassed.
