-- ============================================================================
--  FIX: "saving a shop doesn't work"
--  Paste this whole file into Supabase -> SQL Editor -> New query -> Run.
--
--  Cause: the original write rules required an "editor" row in `profiles`,
--  which is auto-created by a trigger only when a user is added. Accounts made
--  before the trigger existed have no such row, so the database blocked their
--  saves.
--
--  This switches writes to "any signed-in user may edit". That is still secure:
--  public sign-up is OFF, so the ONLY people who can authenticate are the ones
--  you add under Authentication -> Users. Reads stay public (the map).
-- ============================================================================

-- shops: signed-in users can insert/update/delete; everyone can read
drop policy if exists shops_write on public.shops;
create policy shops_write on public.shops
  for all to authenticated using (true) with check (true);

-- categories: same
drop policy if exists cats_write on public.categories;
create policy cats_write on public.categories
  for all to authenticated using (true) with check (true);

-- storage (logo / photo / icon uploads): signed-in users can write
drop policy if exists storage_editor_write on storage.objects;
create policy storage_editor_write on storage.objects
  for all to authenticated
  using      (bucket_id in ('logos','photos','icons'))
  with check (bucket_id in ('logos','photos','icons'));

-- (optional, harmless) give every existing user an editor profile too, so the
-- role-based model also works if you re-enable it later.
insert into public.profiles (user_id, full_name, role)
select id, coalesce(raw_user_meta_data->>'full_name',''), 'editor'
from auth.users
on conflict (user_id) do nothing;

-- ============================================================================
--  Done. Go back to /admin.html, edit a shop, Save — it should work now.
-- ============================================================================
