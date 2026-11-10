-- Data removal (audit 2026-11-11, DB-11 … DB-12). See docs/security.md.
--
-- DB-11 deleting a project (or workspace) left its raw files in Storage forever. Deleted
--       raw_files rows now queue their object; the storage-janitor edge function removes it
--       through the Storage API and sweeps objects that no row references.
--       raw_files.storage_path is client-written text, so it must name its own project:
--       otherwise a row pointing at another tenant's object would make the (service-role)
--       janitor delete that tenant's file.
-- DB-12 deleting an account left the personal workspace, its projects and files behind.
--       delete_account_data() removes every workspace the user is the only member of and
--       refuses while they are the only owner of a team that has other members.

-- ------------------------------------------------------------------ raw file paths

alter table public.raw_files
  add constraint raw_files_path_matches_project
  -- coalesce: a malformed path yields null, and a CHECK lets null through
  check (coalesce(public.storage_path_project(storage_path) = project_id, false));
create index raw_files_storage_path_idx on public.raw_files (storage_path);

-- ------------------------------------------------------------------ deletion queue

create table public.storage_deletions (
  id bigint generated always as identity primary key,
  bucket_id text not null,
  name text not null,
  enqueued_at timestamptz not null default now(),
  attempts integer not null default 0,
  last_error text
);
alter table public.storage_deletions enable row level security;  -- no policies: service role only
revoke all on public.storage_deletions from anon, authenticated;

create or replace function public.enqueue_raw_file_deletion()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
begin
  insert into public.storage_deletions (bucket_id, name) values ('raw-files', old.storage_path);
  return null;
end;
$$;
create trigger raw_files_enqueue_deletion
  after delete on public.raw_files
  for each row execute function public.enqueue_raw_file_deletion();

-- Next batch for the janitor. Entries whose object another raw_files row still references are
-- dropped (two rows may name one object; deleting one row must not delete the other's file).
create or replace function public.claim_storage_deletions(p_limit integer default 500)
returns table (id bigint, bucket_id text, name text)
language plpgsql
security definer
set search_path = ''
as $$
begin
  delete from public.storage_deletions d
  where exists (select 1 from public.raw_files f where f.storage_path = d.name);
  return query
    select d.id, d.bucket_id, d.name
    from public.storage_deletions d
    order by d.id
    limit least(greatest(p_limit, 1), 1000);
end;
$$;

-- Objects no raw_files row references (failed imports, rows deleted before this migration),
-- older than a day so an upload in progress is never swept.
create or replace function public.storage_orphans(p_limit integer default 500)
returns setof text
language sql
stable
security definer
set search_path = ''
as $$
  select o.name
  from storage.objects o
  where o.bucket_id = 'raw-files'
    and o.created_at < now() - interval '1 day'
    and not exists (select 1 from public.raw_files f where f.storage_path = o.name)
  order by o.created_at
  limit least(greatest(p_limit, 1), 1000);
$$;

-- Workspaces nobody belongs to any more (e.g. created before account deletion existed).
create or replace function public.purge_memberless_workspaces()
returns integer
language plpgsql
security definer
set search_path = ''
as $$
declare
  n integer;
begin
  delete from public.workspaces w
  where not exists (select 1 from public.workspace_members m where m.workspace_id = w.id);
  get diagnostics n = row_count;
  return n;
end;
$$;

-- ------------------------------------------------------------------ account deletion

-- Team workspaces the user alone owns while others still belong to them.
create or replace function public.account_deletion_blockers(p_user uuid)
returns table (workspace_id uuid, name text)
language sql
stable
security definer
set search_path = ''
as $$
  select w.id, w.name
  from public.workspaces w
  join public.workspace_members m on m.workspace_id = w.id and m.user_id = p_user and m.role = 'owner'
  where not w.personal
    and not exists (
      select 1 from public.workspace_members o
      where o.workspace_id = w.id and o.role = 'owner' and o.user_id <> p_user)
    and exists (
      select 1 from public.workspace_members x
      where x.workspace_id = w.id and x.user_id <> p_user);
$$;

-- For the account page: what must be handed over before the account can be deleted.
create or replace function public.my_account_deletion_blockers()
returns table (workspace_id uuid, name text)
language sql
stable
security definer
set search_path = ''
as $$
  select b.workspace_id, b.name from public.account_deletion_blockers((select auth.uid())) b;
$$;

-- Deletes every workspace the user is the only member of (personal included); cascades remove
-- projects, children, runs, audit events, and queue the stored files. The auth user itself is
-- deleted afterwards by the delete-account edge function.
create or replace function public.delete_account_data(p_user uuid)
returns integer
language plpgsql
security definer
set search_path = ''
as $$
declare
  n integer;
begin
  if exists (select 1 from public.account_deletion_blockers(p_user)) then
    raise exception using
      errcode = 'P0001',
      message = 'sole_owner_of_team',
      hint = 'Transfer ownership or remove the other members first.';
  end if;
  delete from public.workspaces w
  where exists (select 1 from public.workspace_members m where m.workspace_id = w.id and m.user_id = p_user)
    and not exists (
      select 1 from public.workspace_members o where o.workspace_id = w.id and o.user_id <> p_user);
  get diagnostics n = row_count;
  return n;
end;
$$;

-- ------------------------------------------------------------------ privileges

revoke execute on function public.enqueue_raw_file_deletion() from public, anon, authenticated;
revoke execute on function public.claim_storage_deletions(integer) from public, anon, authenticated;
revoke execute on function public.storage_orphans(integer) from public, anon, authenticated;
revoke execute on function public.purge_memberless_workspaces() from public, anon, authenticated;
revoke execute on function public.account_deletion_blockers(uuid) from public, anon, authenticated;
revoke execute on function public.delete_account_data(uuid) from public, anon, authenticated;
revoke execute on function public.my_account_deletion_blockers() from public, anon;
grant execute on function
  public.claim_storage_deletions(integer),
  public.storage_orphans(integer),
  public.purge_memberless_workspaces(),
  public.account_deletion_blockers(uuid),
  public.delete_account_data(uuid)
to service_role;
grant execute on function public.my_account_deletion_blockers() to authenticated;
