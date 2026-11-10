-- Isolation inside a workspace (audit 2026-11-11). See docs/security.md, findings DB-7 … DB-9.
--
-- DB-7  every member could write; there was no read-only role. Writes now need owner, admin
--       or member; 'viewer' (previous migration) reads only.
-- DB-8  any member could delete a team project, or move it into their personal workspace and
--       take the data with them. Delete is owner/admin; a move needs owner/admin on both sides.
-- DB-9  storage access followed the workspace segment of the object path, so a moved project's
--       files stayed readable by the old workspace. Access now follows the project segment;
--       uploads must name the project's current workspace; the bucket accepts survey file
--       types only.

-- ------------------------------------------------------------------ helpers

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
      and m.user_id = (select auth.uid())
      and m.role in ('owner', 'admin', 'member')
  );
$$;

-- Project id from a storage object path "{workspace_id}/{project_id}/{file}"; null if malformed.
create or replace function public.storage_path_project(p_name text)
returns uuid
language plpgsql
immutable
set search_path = ''
as $$
declare
  seg text := split_part(p_name, '/', 2);
begin
  if seg ~* '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$' then
    return seg::uuid;
  end if;
  return null;
end;
$$;

-- The path's workspace segment is the project's current workspace.
create or replace function public.storage_path_in_project(p_name text)
returns boolean
language sql
stable
security definer
set search_path = ''
as $$
  select exists (
    select 1 from public.projects p
    where p.id = public.storage_path_project(p_name)
      and p.workspace_id = public.storage_path_workspace(p_name)
  );
$$;

-- ------------------------------------------------------------------ projects

drop policy projects_insert on public.projects;
drop policy projects_update on public.projects;
drop policy projects_delete on public.projects;

create policy projects_insert on public.projects for insert to authenticated
  with check (public.has_workspace_role(
    workspace_id, array['owner', 'admin', 'member']::public.workspace_role[]));
create policy projects_update on public.projects for update to authenticated
  using (public.has_workspace_role(
    workspace_id, array['owner', 'admin', 'member']::public.workspace_role[]))
  with check (public.has_workspace_role(
    workspace_id, array['owner', 'admin', 'member']::public.workspace_role[]));
create policy projects_delete on public.projects for delete to authenticated
  using (public.has_workspace_role(workspace_id, array['owner', 'admin']::public.workspace_role[]));

create or replace function public.guard_project_move()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
begin
  if (select auth.uid()) is null or new.workspace_id = old.workspace_id then
    return new;  -- service role / unchanged
  end if;
  if not (public.has_workspace_role(old.workspace_id, array['owner', 'admin']::public.workspace_role[])
          and public.has_workspace_role(new.workspace_id, array['owner', 'admin']::public.workspace_role[])) then
    raise exception using
      errcode = '42501',
      message = 'project_move_forbidden',
      hint = 'Moving a project needs the owner or admin role in both workspaces.';
  end if;
  return new;
end;
$$;

create trigger projects_guard_move
  before update of workspace_id on public.projects
  for each row execute function public.guard_project_move();

-- ------------------------------------------------------------------ project children

do $$
declare
  t text;
begin
  foreach t in array array[
    'control_points', 'raw_files', 'setups', 'observations', 'traverses'
  ] loop
    execute format('drop policy %1$s_insert on public.%1$I', t);
    execute format('drop policy %1$s_update on public.%1$I', t);
    execute format('drop policy %1$s_delete on public.%1$I', t);
    execute format(
      'create policy %1$s_insert on public.%1$I for insert to authenticated with check (public.can_write_project(project_id))', t);
    execute format(
      'create policy %1$s_update on public.%1$I for update to authenticated using (public.can_write_project(project_id)) with check (public.can_write_project(project_id))', t);
    execute format(
      'create policy %1$s_delete on public.%1$I for delete to authenticated using (public.can_write_project(project_id))', t);
  end loop;
end;
$$;

drop policy computation_runs_insert on public.computation_runs;
drop policy computation_runs_delete on public.computation_runs;
drop policy computed_points_insert on public.computed_points;
drop policy computed_points_delete on public.computed_points;
create policy computation_runs_insert on public.computation_runs for insert to authenticated
  with check (public.can_write_project(project_id));
create policy computation_runs_delete on public.computation_runs for delete to authenticated
  using (public.can_write_project(project_id));
create policy computed_points_insert on public.computed_points for insert to authenticated
  with check (public.can_write_project(project_id));
create policy computed_points_delete on public.computed_points for delete to authenticated
  using (public.can_write_project(project_id));

-- ------------------------------------------------------------------ storage

drop policy raw_files_objects_select on storage.objects;
drop policy raw_files_objects_insert on storage.objects;
drop policy raw_files_objects_update on storage.objects;
drop policy raw_files_objects_delete on storage.objects;

create policy raw_files_objects_select on storage.objects for select to authenticated
  using (
    bucket_id = 'raw-files'
    and public.can_access_project(public.storage_path_project(name))
  );
create policy raw_files_objects_insert on storage.objects for insert to authenticated
  with check (
    bucket_id = 'raw-files'
    and public.can_write_project(public.storage_path_project(name))
    and public.storage_path_in_project(name)
  );
create policy raw_files_objects_update on storage.objects for update to authenticated
  using (
    bucket_id = 'raw-files'
    and public.can_write_project(public.storage_path_project(name))
  )
  with check (
    bucket_id = 'raw-files'
    and public.can_write_project(public.storage_path_project(name))
    and public.storage_path_in_project(name)
  );
create policy raw_files_objects_delete on storage.objects for delete to authenticated
  using (
    bucket_id = 'raw-files'
    and public.can_write_project(public.storage_path_project(name))
  );

-- survey files only: the web app sets one of these (web/src/lib/rawFiles.ts); nothing that a
-- browser would render (html, svg, scripts) can be stored
update storage.buckets
set allowed_mime_types = array[
  'text/plain', 'text/csv', 'application/xml', 'text/xml', 'application/dxf',
  'application/octet-stream'
]
where id = 'raw-files';

-- ------------------------------------------------------------------ privileges

revoke execute on function public.guard_project_move() from public, anon, authenticated;
revoke execute on function public.can_write_project(uuid) from public, anon;
revoke execute on function public.storage_path_project(text) from public, anon;
revoke execute on function public.storage_path_in_project(text) from public, anon;
grant execute on function
  public.can_write_project(uuid),
  public.storage_path_project(text),
  public.storage_path_in_project(text)
to authenticated, service_role;
