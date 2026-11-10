-- Append-only audit trail (audit 2026-11-11, DB-10). See docs/security.md.
--
-- Who created, renamed, archived, moved or deleted a project; who changed membership; who
-- uploaded or deleted a file, saved or deleted a run, exported. Rows are written only by the
-- security-definer functions below; nobody (not even service_role) may update or delete them.
-- Owners and admins of a workspace read its events. Deleting a workspace deletes its events
-- (erasure); deleting a user keeps their events with the actor set to null.

create table public.audit_events (
  id bigint generated always as identity primary key,
  workspace_id uuid not null references public.workspaces (id) on delete cascade,
  project_id uuid,  -- no FK: events outlive the project
  actor uuid references auth.users (id) on delete set null,
  action text not null check (action ~ '^[a-z_]+\.[a-z_]+$' and length(action) <= 64),
  details jsonb not null default '{}'::jsonb
    check (jsonb_typeof(details) = 'object' and pg_column_size(details) <= 4096),
  created_at timestamptz not null default now()
);
create index audit_events_workspace_idx on public.audit_events (workspace_id, created_at desc);
create index audit_events_project_idx on public.audit_events (project_id, created_at desc);
create index audit_events_actor_idx on public.audit_events (actor);  -- user deletion sets it null

alter table public.audit_events enable row level security;
create policy audit_events_select on public.audit_events for select to authenticated
  using (public.has_workspace_role(workspace_id, array['owner', 'admin']::public.workspace_role[]));

revoke all on public.audit_events from anon, authenticated, service_role;
grant select on public.audit_events to authenticated, service_role;

-- ------------------------------------------------------------------ writer

-- Inserts one event unless its workspace is gone (a cascade from a workspace delete).
create or replace function public.audit(
  p_workspace_id uuid,
  p_project_id uuid,
  p_action text,
  p_details jsonb default '{}'::jsonb
)
returns void
language plpgsql
security definer
set search_path = ''
as $$
begin
  if not exists (select 1 from public.workspaces w where w.id = p_workspace_id) then
    return;
  end if;
  insert into public.audit_events (workspace_id, project_id, actor, action, details)
  values (p_workspace_id, p_project_id, (select auth.uid()), p_action, coalesce(p_details, '{}'::jsonb));
end;
$$;

-- Workspace of a project, or null when the project is gone (cascade from a project delete).
create or replace function public.project_workspace(p_project_id uuid)
returns uuid
language sql
stable
security definer
set search_path = ''
as $$
  select p.workspace_id from public.projects p where p.id = p_project_id;
$$;

-- ------------------------------------------------------------------ triggers

create or replace function public.audit_projects()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
begin
  if tg_op = 'INSERT' then
    perform public.audit(new.workspace_id, new.id, 'project.created', jsonb_build_object('name', left(new.name, 200)));
  elsif tg_op = 'DELETE' then
    perform public.audit(old.workspace_id, old.id, 'project.deleted', jsonb_build_object('name', left(old.name, 200)));
  else
    if new.workspace_id <> old.workspace_id then
      perform public.audit(old.workspace_id, new.id, 'project.moved_out', jsonb_build_object('to', new.workspace_id));
      perform public.audit(new.workspace_id, new.id, 'project.moved_in', jsonb_build_object('from', old.workspace_id));
    end if;
    if new.name <> old.name then
      perform public.audit(new.workspace_id, new.id, 'project.renamed',
        jsonb_build_object('from', left(old.name, 200), 'to', left(new.name, 200)));
    end if;
    if new.archived_at is distinct from old.archived_at then
      perform public.audit(new.workspace_id, new.id,
        case when new.archived_at is null then 'project.restored' else 'project.archived' end);
    end if;
  end if;
  return null;
end;
$$;
create trigger projects_audit
  after insert or update or delete on public.projects
  for each row execute function public.audit_projects();

create or replace function public.audit_members()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
begin
  if tg_op = 'INSERT' then
    perform public.audit(new.workspace_id, null, 'member.added',
      jsonb_build_object('user_id', new.user_id, 'role', new.role));
  elsif tg_op = 'DELETE' then
    perform public.audit(old.workspace_id, null, 'member.removed',
      jsonb_build_object('user_id', old.user_id, 'role', old.role));
  elsif new.role <> old.role then
    perform public.audit(new.workspace_id, null, 'member.role_changed',
      jsonb_build_object('user_id', new.user_id, 'from', old.role, 'to', new.role));
  end if;
  return null;
end;
$$;
create trigger workspace_members_audit
  after insert or update or delete on public.workspace_members
  for each row execute function public.audit_members();

create or replace function public.audit_workspaces()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
begin
  if tg_op = 'INSERT' then
    perform public.audit(new.id, null, 'workspace.created', jsonb_build_object('name', left(new.name, 200)));
  elsif new.name <> old.name then
    perform public.audit(new.id, null, 'workspace.renamed',
      jsonb_build_object('from', left(old.name, 200), 'to', left(new.name, 200)));
  end if;
  return null;
end;
$$;
create trigger workspaces_audit
  after insert or update of name on public.workspaces
  for each row execute function public.audit_workspaces();

create or replace function public.audit_project_children()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
declare
  -- one function for two tables: read the row as JSON (record fields resolve at plan time)
  r jsonb;
  ws uuid;
  is_file boolean := tg_table_name = 'raw_files';
  verb text;
begin
  if tg_op = 'DELETE' then
    r := to_jsonb(old);
  else
    r := to_jsonb(new);
  end if;
  ws := public.project_workspace((r ->> 'project_id')::uuid);
  if ws is null then
    return null;  -- the project itself is being deleted: 'project.deleted' covers it
  end if;
  verb := case
    when tg_op = 'DELETE' then 'deleted'
    when is_file then 'uploaded'
    else 'saved'
  end;
  perform public.audit(
    ws,
    (r ->> 'project_id')::uuid,
    case when is_file then 'file.' else 'run.' end || verb,
    case when is_file
      then jsonb_build_object('file_id', r -> 'id', 'filename', left(r ->> 'filename', 255))
      else jsonb_build_object('run_id', r -> 'id')
    end
  );
  return null;
end;
$$;
create trigger raw_files_audit
  after insert or delete on public.raw_files
  for each row execute function public.audit_project_children();
create trigger computation_runs_audit
  after insert or delete on public.computation_runs
  for each row execute function public.audit_project_children();

-- ------------------------------------------------------------------ RPC: exports

-- Called by the engine API with the caller's JWT after an export of a stored project.
create or replace function public.log_export(p_project_id uuid, p_format text)
returns void
language plpgsql
security definer
set search_path = ''
as $$
begin
  if not public.can_access_project(p_project_id) then
    raise exception using errcode = '42501', message = 'project_not_accessible';
  end if;
  if p_format !~ '^[a-z0-9_]{1,16}$' then
    raise exception using errcode = '22023', message = 'invalid_format';
  end if;
  perform public.audit(public.project_workspace(p_project_id), p_project_id, 'project.exported',
    jsonb_build_object('format', p_format));
end;
$$;

-- ------------------------------------------------------------------ privileges

revoke execute on function public.audit(uuid, uuid, text, jsonb) from public, anon, authenticated;
revoke execute on function public.project_workspace(uuid) from public, anon, authenticated;
revoke execute on function public.audit_projects() from public, anon, authenticated;
revoke execute on function public.audit_members() from public, anon, authenticated;
revoke execute on function public.audit_workspaces() from public, anon, authenticated;
revoke execute on function public.audit_project_children() from public, anon, authenticated;
revoke execute on function public.log_export(uuid, text) from public, anon;
grant execute on function public.log_export(uuid, text) to authenticated;
