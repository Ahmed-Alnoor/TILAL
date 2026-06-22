-- ============================================================================
--  Tilal Mall — shop editor backend schema  (Supabase / Postgres)
--  Run ONCE in the Supabase dashboard → SQL Editor → New query → Run.
--  Safe to re-run: every statement is idempotent.
--
--  Security model (answers "can no one else log in / edit?"):
--    • Reading shop data is PUBLIC  (it's a public directory).
--    • Writing requires a logged-in user listed in `profiles` as an editor.
--    • That rule is enforced HERE, on the server, by Row-Level Security —
--      it cannot be bypassed from the website's JavaScript.
--    • The website only ever holds the *anon* key (safe to publish). The
--      powerful *service_role* key is used only by the one-time seed script
--      on your machine and must never be committed or put in the browser.
-- ============================================================================

-- ---------------------------------------------------------------------------
-- 1. profiles — one row per human editor; this is the allow-list for writes
-- ---------------------------------------------------------------------------
create table if not exists public.profiles (
  user_id    uuid primary key references auth.users(id) on delete cascade,
  full_name  text,
  role       text not null default 'editor' check (role in ('editor','admin')),
  created_at timestamptz not null default now()
);

-- when you invite a user (dashboard → Authentication → Users), auto-give them
-- an editor profile so they can start editing. Promote to 'admin' by hand.
create or replace function public.handle_new_user()
returns trigger language plpgsql security definer set search_path = public as $$
begin
  insert into public.profiles (user_id, full_name)
  values (new.id, coalesce(new.raw_user_meta_data->>'full_name',''))
  on conflict (user_id) do nothing;
  return new;
end; $$;

drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created
  after insert on auth.users
  for each row execute function public.handle_new_user();

-- SECURITY DEFINER helpers: they bypass RLS internally, which also avoids the
-- classic "policy on profiles selects from profiles" infinite-recursion trap.
create or replace function public.is_editor()
returns boolean language sql stable security definer set search_path = public as $$
  select exists (select 1 from public.profiles
                 where user_id = auth.uid() and role in ('editor','admin'));
$$;

create or replace function public.is_admin()
returns boolean language sql stable security definer set search_path = public as $$
  select exists (select 1 from public.profiles
                 where user_id = auth.uid() and role = 'admin');
$$;

-- ---------------------------------------------------------------------------
-- 2. categories — per-category look + default copy (optional, Phase 5)
-- ---------------------------------------------------------------------------
create table if not exists public.categories (
  key         text primary key,        -- e.g. 'line-shop', 'hypermarket'
  label       text,
  color       integer,                 -- 0xRRGGBB as a plain int
  height      real,
  tag         text,
  description text,
  icon        text,
  is_landmark boolean default false,
  updated_at  timestamptz not null default now()
);

-- ---------------------------------------------------------------------------
-- 3. shops — per-shop editable details, keyed to the baked unit id
--    (category is plain text on purpose: no FK, so unknown/new categories
--     never block a save — the map falls back to its default look.)
-- ---------------------------------------------------------------------------
create table if not exists public.shops (
  id           text primary key,       -- matches the unit id, e.g. 'GF-025'
  floor        text,                   -- 'BL' | 'G' | 'F1'
  name         text,
  category     text,
  description  text,
  area_m2      numeric,
  logo_url     text,
  photo_url    text,
  icon         text,
  phone        text,
  hours        text,
  website      text,
  is_published boolean not null default true,
  updated_at   timestamptz not null default now(),
  updated_by   uuid references auth.users(id)
);

create index if not exists shops_floor_idx    on public.shops(floor);
create index if not exists shops_category_idx on public.shops(category);

-- stamp who edited and when, on every write
create or replace function public.touch_shop()
returns trigger language plpgsql as $$
begin
  new.updated_at := now();
  new.updated_by := auth.uid();
  return new;
end; $$;

drop trigger if exists shops_touch on public.shops;
create trigger shops_touch before insert or update on public.shops
  for each row execute function public.touch_shop();

-- ---------------------------------------------------------------------------
-- 4. Row-Level Security — public read, editor-only write
-- ---------------------------------------------------------------------------
alter table public.shops      enable row level security;
alter table public.categories enable row level security;
alter table public.profiles   enable row level security;

-- shops: anyone may read; only editors may insert/update/delete
drop policy if exists shops_read  on public.shops;
create policy shops_read  on public.shops for select using (true);
drop policy if exists shops_write on public.shops;
create policy shops_write on public.shops for all
  using (public.is_editor()) with check (public.is_editor());

-- categories: same shape
drop policy if exists cats_read  on public.categories;
create policy cats_read  on public.categories for select using (true);
drop policy if exists cats_write on public.categories;
create policy cats_write on public.categories for all
  using (public.is_editor()) with check (public.is_editor());

-- profiles: you can read your own row; admins can read all; only admins edit roles
drop policy if exists profiles_read  on public.profiles;
create policy profiles_read  on public.profiles for select
  using (auth.uid() = user_id or public.is_admin());
drop policy if exists profiles_write on public.profiles;
create policy profiles_write on public.profiles for all
  using (public.is_admin()) with check (public.is_admin());

-- ---------------------------------------------------------------------------
-- 5. Storage buckets for logos / photos / custom icons (public read)
-- ---------------------------------------------------------------------------
insert into storage.buckets (id, name, public) values
  ('logos','logos',true), ('photos','photos',true), ('icons','icons',true)
on conflict (id) do nothing;

-- editor-only uploads/edits/deletes; public read is automatic for public buckets
drop policy if exists storage_editor_write on storage.objects;
create policy storage_editor_write on storage.objects for all to authenticated
  using      (bucket_id in ('logos','photos','icons') and public.is_editor())
  with check (bucket_id in ('logos','photos','icons') and public.is_editor());

-- ============================================================================
--  Done. Next: run backend/seed_shops.py to load the 1,144 existing shops,
--  then invite your editors under Authentication → Users.
-- ============================================================================
