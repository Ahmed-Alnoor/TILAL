-- ============================================================================
--  OPTIONAL hardening — "defence in depth" for the shop editor.
--  Paste into Supabase -> SQL Editor -> Run. Safe: it will NOT lock out anyone
--  who can edit today.
--
--  What it changes:
--   1. Everyone who exists right now stays an editor (no lockout).
--   2. Any NEW account defaults to a non-editing "viewer" role.
--   3. Writing shop data requires an editor/admin role — not just any login.
--
--  Why: even if email sign-up is ever turned on by accident, a stranger who
--  registers would land as a powerless "viewer" and still could not edit.
--  (Your PRIMARY protection is still keeping sign-up disabled — see SECURITY.md.)
--
--  Trade-off: to add a new editor later you create the user, then set their
--  role to 'editor' in Table editor -> profiles (one click).
-- ============================================================================

-- allow a third, read-only role
alter table public.profiles drop constraint if exists profiles_role_check;
alter table public.profiles add constraint profiles_role_check
  check (role in ('viewer','editor','admin'));

-- 1. keep all current users as editors (prevents any lockout)
insert into public.profiles (user_id, role)
  select id, 'editor' from auth.users
  on conflict (user_id) do nothing;

-- 2. new accounts from now on are viewers (cannot edit) until promoted
create or replace function public.handle_new_user()
returns trigger language plpgsql security definer set search_path = public as $$
begin
  insert into public.profiles (user_id, full_name, role)
  values (new.id, coalesce(new.raw_user_meta_data->>'full_name',''), 'viewer')
  on conflict (user_id) do nothing;
  return new;
end; $$;

-- 3. writes require an editor/admin role again (reads stay public)
drop policy if exists shops_write on public.shops;
create policy shops_write on public.shops for all to authenticated
  using (public.is_editor()) with check (public.is_editor());

drop policy if exists cats_write on public.categories;
create policy cats_write on public.categories for all to authenticated
  using (public.is_editor()) with check (public.is_editor());

drop policy if exists storage_editor_write on storage.objects;
create policy storage_editor_write on storage.objects for all to authenticated
  using      (bucket_id in ('logos','photos','icons') and public.is_editor())
  with check (bucket_id in ('logos','photos','icons') and public.is_editor());

-- ============================================================================
--  Done. To make someone an admin (can manage users): Table editor -> profiles
--  -> set their role to 'admin'.
-- ============================================================================
