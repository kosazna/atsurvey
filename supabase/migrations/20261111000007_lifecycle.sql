-- Project lifecycle (security plan phase 4): trash with 30-day recovery, archive/restore under
-- the plan limit, duplicate, named runs.
--
-- * Deleting a project moves it to the trash (owner/admin); it can be restored for 30 days,
--   then the storage-janitor purges it (cascade → files queued for erasure). "Delete forever"
--   is the existing hard delete (owner/admin).
-- * Trashed projects are read-only and count neither towards the free-plan limit nor as active.
-- * duplicate_project() runs with the caller's rights (RLS, row caps, plan limit all apply).
-- * Runs get an editable label; every other run column stays immutable.

alter table public.projects add column deleted_at timestamptz;
create index projects_deleted_idx on public.projects (deleted_at) where deleted_at is not null;

alter table public.computation_runs
  add column label text check (label is null or length(label) <= 200);

-- ------------------------------------------------------------------ writes stop in the trash

create or replace function public.can_write_project(p_project_id uuid)
returns boolean
language sql
stable
security definer
set search_path = ''
as $$
  select exists (
    select 1
    from public.projects p
    join public.workspace_members m on m.workspace_id = p.workspace_id
    where p.id = p_project_id
      and p.deleted_at is null
      and m.user_id = (select auth.uid())
      and m.role in ('owner', 'admin', 'member')
      and public.mfa_satisfied(p.workspace_id)
  );
$$;

-- ------------------------------------------------------------------ plan limit

create or replace function public.enforce_project_limit()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
declare
  active_count integer;
  becomes_active boolean;
begin
  becomes_active := new.archived_at is null and new.deleted_at is null and (
    tg_op = 'INSERT'
    or old.archived_at is not null
    or old.deleted_at is not null
    or new.workspace_id <> old.workspace_id
  );
  if not becomes_active or public.workspace_plan(new.workspace_id) = 'pro' then
    return new;
  end if;
  select count(*) into active_count
  from public.projects p
  where p.workspace_id = new.workspace_id and p.archived_at is null and p.deleted_at is null
    and p.id <> new.id;
  if active_count >= 3 then
    raise exception using
      errcode = 'P0001',
      message = 'project_limit_reached',
      detail = 'The free plan allows 3 active projects.',
      hint = 'Archive a project or upgrade to Pro.';
  end if;
  return new;
end;
$$;

drop trigger if exists projects_enforce_limit on public.projects;
create trigger projects_enforce_limit
  before insert or update of archived_at, deleted_at, workspace_id on public.projects
  for each row execute function public.enforce_project_limit();

-- ------------------------------------------------------------------ trash

create or replace function public.trash_project(p_project_id uuid)
returns void
language plpgsql
security definer
set search_path = ''
as $$
declare
  ws uuid := public.project_workspace(p_project_id);
begin
  if ws is null or not public.has_workspace_role(ws, array['owner', 'admin']::public.workspace_role[]) then
    raise exception using errcode = '42501', message = 'not_allowed';
  end if;
  update public.projects set deleted_at = now() where id = p_project_id and deleted_at is null;
  perform public.audit(ws, p_project_id, 'project.trashed');
end;
$$;

create or replace function public.restore_project(p_project_id uuid)
returns void
language plpgsql
security definer
set search_path = ''
as $$
declare
  ws uuid := public.project_workspace(p_project_id);
begin
  if ws is null or not public.has_workspace_role(ws, array['owner', 'admin']::public.workspace_role[]) then
    raise exception using errcode = '42501', message = 'not_allowed';
  end if;
  update public.projects set deleted_at = null where id = p_project_id and deleted_at is not null;
  perform public.audit(ws, p_project_id, 'project.untrashed');
end;
$$;

-- Service role (storage-janitor): projects in the trash for more than 30 days.
create or replace function public.purge_trashed_projects()
returns integer
language plpgsql
security definer
set search_path = ''
as $$
declare
  n integer;
begin
  delete from public.projects where deleted_at < now() - interval '30 days';
  get diagnostics n = row_count;
  return n;
end;
$$;

-- ------------------------------------------------------------------ duplicate

create or replace function public.duplicate_project(p_project_id uuid, p_name text)
returns uuid
language plpgsql
security invoker
set search_path = ''
as $$
declare
  src public.projects;
  new_id uuid;
  s record;
  new_setup uuid;
begin
  select * into src from public.projects where id = p_project_id and deleted_at is null;
  if not found then
    raise exception using errcode = 'P0001', message = 'project_not_found';
  end if;
  insert into public.projects (workspace_id, name, description, crs_epsg, angle_unit, settings, extras)
  values (src.workspace_id, left(coalesce(nullif(trim(p_name), ''), src.name), 200), src.description,
          src.crs_epsg, src.angle_unit, src.settings, src.extras)
  returning id into new_id;

  insert into public.control_points (project_id, name, x, y, z, code, note)
  select new_id, name, x, y, z, code, note from public.control_points where project_id = p_project_id;

  for s in select * from public.setups where project_id = p_project_id order by ordinal loop
    insert into public.setups (project_id, ordinal, station, instrument_height, backsight, note)
    values (new_id, s.ordinal, s.station, s.instrument_height, s.backsight, s.note)
    returning id into new_setup;
    insert into public.observations (setup_id, ordinal, target, hz, v, sd, target_height, code, excluded, edited)
    select new_setup, ordinal, target, hz, v, sd, target_height, code, excluded, edited
    from public.observations where setup_id = s.id;
  end loop;

  insert into public.traverses (project_id, ordinal, name, route, kind, end_orientation, enabled)
  select new_id, ordinal, name, route, kind, end_orientation, enabled
  from public.traverses where project_id = p_project_id;

  return new_id;  -- audited as project.created by the projects trigger
end;
$$;

-- ------------------------------------------------------------------ run labels

grant update (label) on public.computation_runs to authenticated;
create policy computation_runs_update_label on public.computation_runs for update to authenticated
  using (public.can_write_project(project_id))
  with check (public.can_write_project(project_id));

-- ------------------------------------------------------------------ privileges

revoke execute on function public.trash_project(uuid) from public, anon;
revoke execute on function public.restore_project(uuid) from public, anon;
revoke execute on function public.duplicate_project(uuid, text) from public, anon;
revoke execute on function public.purge_trashed_projects() from public, anon, authenticated;
grant execute on function
  public.trash_project(uuid),
  public.restore_project(uuid),
  public.duplicate_project(uuid, text)
to authenticated;
grant execute on function public.purge_trashed_projects() to service_role;
