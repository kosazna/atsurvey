-- atsurvey initial schema
-- Source of truth: docs/contracts.md (Database section).
-- All angles stored in radians, coordinates in EPSG:2100 (EGSA87) metres.

create schema if not exists extensions;
create extension if not exists postgis with schema extensions;

-- ---------------------------------------------------------------- enums

create type public.workspace_role as enum ('owner', 'admin', 'member');
create type public.point_kind as enum ('control', 'traverse', 'detail');

-- ---------------------------------------------------------------- generic helpers

create or replace function public.set_updated_at()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
  new.updated_at := now();
  return new;
end;
$$;

-- ---------------------------------------------------------------- tables

create table public.profiles (
  id uuid primary key references auth.users (id) on delete cascade,
  full_name text,
  locale text not null default 'el' check (locale in ('el', 'en')),
  created_at timestamptz not null default now()
);

create table public.workspaces (
  id uuid primary key default gen_random_uuid(),
  name text not null check (length(trim(name)) > 0),
  personal boolean not null default false,
  created_by uuid references auth.users (id) on delete set null default auth.uid(),
  created_at timestamptz not null default now()
);
create index workspaces_created_by_idx on public.workspaces (created_by);

create table public.workspace_members (
  workspace_id uuid not null references public.workspaces (id) on delete cascade,
  user_id uuid not null references auth.users (id) on delete cascade,
  role public.workspace_role not null default 'member',
  created_at timestamptz not null default now(),
  primary key (workspace_id, user_id)
);
create index workspace_members_user_idx on public.workspace_members (user_id);

create table public.projects (
  id uuid primary key default gen_random_uuid(),
  workspace_id uuid not null references public.workspaces (id) on delete cascade,
  name text not null check (length(trim(name)) > 0),
  description text,
  crs_epsg integer not null default 2100,
  angle_unit text not null default 'gon' check (angle_unit in ('gon', 'deg', 'dms', 'rad')),
  settings jsonb not null default '{}'::jsonb check (jsonb_typeof(settings) = 'object'),
  created_by uuid references auth.users (id) on delete set null default auth.uid(),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  archived_at timestamptz
);
create index projects_workspace_idx on public.projects (workspace_id);
create index projects_created_by_idx on public.projects (created_by);
create trigger projects_set_updated_at
  before update on public.projects
  for each row execute function public.set_updated_at();

create table public.control_points (
  id uuid primary key default gen_random_uuid(),
  project_id uuid not null references public.projects (id) on delete cascade,
  name text not null check (length(name) > 0),
  x double precision not null,
  y double precision not null,
  z double precision,
  code text,
  note text,
  created_at timestamptz not null default now(),
  unique (project_id, name)
);

create table public.raw_files (
  id uuid primary key default gen_random_uuid(),
  project_id uuid not null references public.projects (id) on delete cascade,
  storage_path text not null,
  filename text not null,
  format text not null,
  size_bytes bigint check (size_bytes is null or size_bytes >= 0),
  sha256 text,
  angle_unit text check (angle_unit is null or angle_unit in ('gon', 'deg', 'dms', 'rad')),
  parser_version text,
  created_by uuid references auth.users (id) on delete set null default auth.uid(),
  created_at timestamptz not null default now(),
  unique (id, project_id)
);
create index raw_files_project_idx on public.raw_files (project_id);
create index raw_files_created_by_idx on public.raw_files (created_by);

create table public.setups (
  id uuid primary key default gen_random_uuid(),
  project_id uuid not null references public.projects (id) on delete cascade,
  raw_file_id uuid,
  ordinal integer not null default 0,
  station text not null check (length(station) > 0),
  instrument_height double precision not null default 0,
  backsight text,
  note text,
  created_at timestamptz not null default now(),
  unique (id, project_id),
  -- composite FK keeps a setup's raw file inside the same project
  foreign key (raw_file_id, project_id)
    references public.raw_files (id, project_id) on delete set null (raw_file_id)
);
create index setups_project_idx on public.setups (project_id, ordinal);
create index setups_raw_file_idx on public.setups (raw_file_id);

create table public.observations (
  id uuid primary key default gen_random_uuid(),
  setup_id uuid not null,
  project_id uuid not null,
  ordinal integer not null default 0,
  target text not null check (length(target) > 0),
  hz double precision not null,
  v double precision,
  sd double precision check (sd is null or sd >= 0),
  target_height double precision not null default 0,
  code text,
  excluded boolean not null default false,
  edited boolean not null default false,
  created_at timestamptz not null default now(),
  foreign key (setup_id, project_id)
    references public.setups (id, project_id) on delete cascade
);
create index observations_setup_idx on public.observations (setup_id, ordinal);
create index observations_project_idx on public.observations (project_id);

create table public.traverses (
  id uuid primary key default gen_random_uuid(),
  project_id uuid not null references public.projects (id) on delete cascade,
  ordinal integer not null default 0,
  name text,
  route text[] not null check (cardinality(route) >= 3),
  kind text not null default 'auto' check (kind in ('auto', 'open', 'link', 'closed')),
  end_orientation boolean,
  enabled boolean not null default true,
  created_at timestamptz not null default now()
);
create index traverses_project_idx on public.traverses (project_id, ordinal);

create table public.computation_runs (
  id uuid primary key default gen_random_uuid(),
  project_id uuid not null references public.projects (id) on delete cascade,
  engine_version text not null,
  input_hash text not null,
  settings jsonb not null default '{}'::jsonb,
  summary jsonb not null default '{}'::jsonb,
  result jsonb not null,
  created_by uuid references auth.users (id) on delete set null default auth.uid(),
  created_at timestamptz not null default now(),
  unique (id, project_id)
);
create index computation_runs_project_idx on public.computation_runs (project_id, created_at desc);
create index computation_runs_created_by_idx on public.computation_runs (created_by);

create table public.computed_points (
  id uuid primary key default gen_random_uuid(),
  run_id uuid not null,
  project_id uuid not null,
  name text not null,
  kind public.point_kind not null,
  code text,
  x double precision not null,
  y double precision not null,
  z double precision,
  geom extensions.geometry(PointZ, 2100) not null,
  foreign key (run_id, project_id)
    references public.computation_runs (id, project_id) on delete cascade
);
create index computed_points_run_idx on public.computed_points (run_id);
create index computed_points_project_idx on public.computed_points (project_id);
create index computed_points_geom_idx on public.computed_points using gist (geom);

create table public.subscriptions (
  workspace_id uuid primary key references public.workspaces (id) on delete cascade,
  provider text not null default 'paddle',
  customer_id text,
  subscription_id text unique,
  plan text not null default 'free' check (plan in ('free', 'pro')),
  status text not null default 'inactive',
  current_period_end timestamptz,
  updated_at timestamptz not null default now()
);
create trigger subscriptions_set_updated_at
  before update on public.subscriptions
  for each row execute function public.set_updated_at();

-- ---------------------------------------------------------------- child project_id sync
-- Clients may omit project_id on observations / computed_points; it is derived from the
-- parent row (security invoker, so the parent must be visible to the caller).

create or replace function public.observations_sync_project()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
  select s.project_id into new.project_id from public.setups s where s.id = new.setup_id;
  return new;
end;
$$;
create trigger observations_sync_project
  before insert or update of setup_id, project_id on public.observations
  for each row execute function public.observations_sync_project();

create or replace function public.computed_points_sync_project()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
  select r.project_id into new.project_id from public.computation_runs r where r.id = new.run_id;
  return new;
end;
$$;
create trigger computed_points_sync_project
  before insert or update of run_id, project_id on public.computed_points
  for each row execute function public.computed_points_sync_project();

-- ---------------------------------------------------------------- access helpers
-- security definer so they can read membership without recursing through RLS.

create or replace function public.is_workspace_member(p_workspace_id uuid)
returns boolean
language sql
stable
security definer
set search_path = ''
as $$
  select exists (
    select 1 from public.workspace_members m
    where m.workspace_id = p_workspace_id and m.user_id = (select auth.uid())
  );
$$;

create or replace function public.has_workspace_role(
  p_workspace_id uuid,
  p_roles public.workspace_role[]
)
returns boolean
language sql
stable
security definer
set search_path = ''
as $$
  select exists (
    select 1 from public.workspace_members m
    where m.workspace_id = p_workspace_id
      and m.user_id = (select auth.uid())
      and m.role = any (p_roles)
  );
$$;

create or replace function public.can_access_project(p_project_id uuid)
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
    where p.id = p_project_id and m.user_id = (select auth.uid())
  );
$$;

-- Workspace id from a storage object path "{workspace_id}/{project_id}/{file}"; null if malformed.
create or replace function public.storage_path_workspace(p_name text)
returns uuid
language plpgsql
immutable
set search_path = ''
as $$
declare
  seg text := split_part(p_name, '/', 1);
begin
  if seg ~* '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$' then
    return seg::uuid;
  end if;
  return null;
end;
$$;

-- ---------------------------------------------------------------- plans / entitlements

create or replace function public.workspace_plan(p_workspace_id uuid)
returns text
language sql
stable
security invoker
set search_path = ''
as $$
  select case when exists (
    select 1 from public.subscriptions s
    where s.workspace_id = p_workspace_id
      and s.plan = 'pro'
      and s.status in ('active', 'trialing')
      and (s.current_period_end is null or s.current_period_end > now())
  ) then 'pro' else 'free' end;
$$;

create or replace function public.enforce_project_limit()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
declare
  active_count integer;
  plan text;
begin
  if tg_op = 'UPDATE' and not (old.archived_at is not null and new.archived_at is null) then
    return new;
  end if;
  if new.archived_at is not null then
    return new;
  end if;
  plan := public.workspace_plan(new.workspace_id);
  if plan = 'pro' then
    return new;
  end if;
  select count(*) into active_count
  from public.projects p
  where p.workspace_id = new.workspace_id and p.archived_at is null and p.id <> new.id;
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
create trigger projects_enforce_limit
  before insert or update of archived_at on public.projects
  for each row execute function public.enforce_project_limit();

-- ---------------------------------------------------------------- new users / workspaces

create or replace function public.add_workspace_owner()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
begin
  if new.created_by is not null then
    insert into public.workspace_members (workspace_id, user_id, role)
    values (new.id, new.created_by, 'owner')
    on conflict (workspace_id, user_id) do update set role = 'owner';
  end if;
  return new;
end;
$$;
create trigger workspaces_add_owner
  after insert on public.workspaces
  for each row execute function public.add_workspace_owner();

create or replace function public.handle_new_user()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
declare
  display_name text := nullif(trim(coalesce(
    new.raw_user_meta_data ->> 'full_name',
    new.raw_user_meta_data ->> 'name',
    ''
  )), '');
begin
  insert into public.profiles (id, full_name, locale)
  values (
    new.id,
    display_name,
    case when new.raw_user_meta_data ->> 'locale' = 'en' then 'en' else 'el' end
  )
  on conflict (id) do nothing;

  insert into public.workspaces (name, personal, created_by)
  values (coalesce(display_name, split_part(coalesce(new.email, ''), '@', 1), 'Workspace'), true, new.id);
  return new;
end;
$$;
create trigger on_auth_user_created
  after insert on auth.users
  for each row execute function public.handle_new_user();

-- ---------------------------------------------------------------- RPC: save a computation run

create or replace function public.save_computation_run(
  p_project_id uuid,
  p_result jsonb,
  p_settings jsonb
)
returns uuid
language plpgsql
security invoker
set search_path = ''
as $$
declare
  v_run_id uuid;
begin
  if p_result is null or jsonb_typeof(p_result) <> 'object' then
    raise exception 'p_result must be a JSON object' using errcode = '22023';
  end if;

  insert into public.computation_runs (project_id, engine_version, input_hash, settings, summary, result)
  values (
    p_project_id,
    coalesce(p_result ->> 'engine_version', 'unknown'),
    coalesce(p_result ->> 'input_hash', ''),
    coalesce(p_settings, '{}'::jsonb),
    coalesce(p_result -> 'summary', '{}'::jsonb),
    p_result
  )
  returning id into v_run_id;

  insert into public.computed_points (run_id, project_id, name, kind, code, x, y, z, geom)
  select
    v_run_id,
    p_project_id,
    p.name,
    p.kind::public.point_kind,
    p.code,
    p.x,
    p.y,
    p.z,
    extensions.st_setsrid(extensions.st_makepoint(p.x, p.y, coalesce(p.z, 0)), 2100)
  from jsonb_to_recordset(coalesce(p_result -> 'points', '[]'::jsonb))
    as p(name text, kind text, code text, x double precision, y double precision, z double precision);

  return v_run_id;
end;
$$;

-- ---------------------------------------------------------------- row level security

alter table public.profiles enable row level security;
alter table public.workspaces enable row level security;
alter table public.workspace_members enable row level security;
alter table public.projects enable row level security;
alter table public.control_points enable row level security;
alter table public.raw_files enable row level security;
alter table public.setups enable row level security;
alter table public.observations enable row level security;
alter table public.traverses enable row level security;
alter table public.computation_runs enable row level security;
alter table public.computed_points enable row level security;
alter table public.subscriptions enable row level security;

-- profiles: own row only (rows are created by the signup trigger)
create policy profiles_select on public.profiles for select to authenticated
  using (id = (select auth.uid()));
create policy profiles_update on public.profiles for update to authenticated
  using (id = (select auth.uid())) with check (id = (select auth.uid()));

-- workspaces
create policy workspaces_select on public.workspaces for select to authenticated
  using (public.is_workspace_member(id) or created_by = (select auth.uid()));
create policy workspaces_insert on public.workspaces for insert to authenticated
  with check (created_by = (select auth.uid()) and personal = false);
create policy workspaces_update on public.workspaces for update to authenticated
  using (public.has_workspace_role(id, array['owner', 'admin']::public.workspace_role[]))
  with check (public.has_workspace_role(id, array['owner', 'admin']::public.workspace_role[]));
create policy workspaces_delete on public.workspaces for delete to authenticated
  using (personal = false and public.has_workspace_role(id, array['owner']::public.workspace_role[]));

-- workspace_members: members see the roster; owners/admins manage it
create policy members_select on public.workspace_members for select to authenticated
  using (public.is_workspace_member(workspace_id));
create policy members_insert on public.workspace_members for insert to authenticated
  with check (public.has_workspace_role(workspace_id, array['owner', 'admin']::public.workspace_role[]));
create policy members_update on public.workspace_members for update to authenticated
  using (public.has_workspace_role(workspace_id, array['owner', 'admin']::public.workspace_role[]))
  with check (public.has_workspace_role(workspace_id, array['owner', 'admin']::public.workspace_role[]));
create policy members_delete on public.workspace_members for delete to authenticated
  using (
    public.has_workspace_role(workspace_id, array['owner', 'admin']::public.workspace_role[])
    or user_id = (select auth.uid())
  );

-- projects
create policy projects_select on public.projects for select to authenticated
  using (public.is_workspace_member(workspace_id));
create policy projects_insert on public.projects for insert to authenticated
  with check (public.is_workspace_member(workspace_id));
create policy projects_update on public.projects for update to authenticated
  using (public.is_workspace_member(workspace_id))
  with check (public.is_workspace_member(workspace_id));
create policy projects_delete on public.projects for delete to authenticated
  using (public.is_workspace_member(workspace_id));

-- project children: same rule for every operation
do $$
declare
  t text;
begin
  foreach t in array array[
    'control_points', 'raw_files', 'setups', 'observations', 'traverses'
  ] loop
    execute format(
      'create policy %1$s_select on public.%1$I for select to authenticated using (public.can_access_project(project_id))', t);
    execute format(
      'create policy %1$s_insert on public.%1$I for insert to authenticated with check (public.can_access_project(project_id))', t);
    execute format(
      'create policy %1$s_update on public.%1$I for update to authenticated using (public.can_access_project(project_id)) with check (public.can_access_project(project_id))', t);
    execute format(
      'create policy %1$s_delete on public.%1$I for delete to authenticated using (public.can_access_project(project_id))', t);
  end loop;
end;
$$;

-- computation runs and their points are immutable (no update policy)
create policy computation_runs_select on public.computation_runs for select to authenticated
  using (public.can_access_project(project_id));
create policy computation_runs_insert on public.computation_runs for insert to authenticated
  with check (public.can_access_project(project_id));
create policy computation_runs_delete on public.computation_runs for delete to authenticated
  using (public.can_access_project(project_id));

create policy computed_points_select on public.computed_points for select to authenticated
  using (public.can_access_project(project_id));
create policy computed_points_insert on public.computed_points for insert to authenticated
  with check (public.can_access_project(project_id));
create policy computed_points_delete on public.computed_points for delete to authenticated
  using (public.can_access_project(project_id));

-- subscriptions: read-only for members; written by service_role (webhook) only
create policy subscriptions_select on public.subscriptions for select to authenticated
  using (public.is_workspace_member(workspace_id));

-- ---------------------------------------------------------------- privileges

revoke all on all tables in schema public from anon;
grant select, insert, update, delete on all tables in schema public to authenticated;
revoke insert, update, delete on public.subscriptions from authenticated;
revoke update on public.computation_runs, public.computed_points from authenticated;
grant all on all tables in schema public to service_role;

revoke execute on all functions in schema public from public, anon;
grant execute on function
  public.is_workspace_member(uuid),
  public.has_workspace_role(uuid, public.workspace_role[]),
  public.can_access_project(uuid),
  public.storage_path_workspace(text),
  public.workspace_plan(uuid),
  public.save_computation_run(uuid, jsonb, jsonb)
to authenticated, service_role;
