-- Security hardening (audit 2026-11-10). See docs/security.md, findings DB-1 … DB-6.
--
-- DB-1  created_by could be set to another user's id (attribution spoofing).
-- DB-2  double precision columns accepted NaN / ±Infinity and absurd magnitudes.
-- DB-3  unbounded text / jsonb sizes (storage abuse, oversized names breaking clients).
-- DB-4  unbounded rows per project / run (storage abuse on the shared database).
-- DB-5  free users could create unlimited team workspaces, each with 3 free projects
--       (paywall bypass of the project limit).
-- DB-6  save_computation_run accepted any payload size and malformed point arrays.

-- ------------------------------------------------------------------ DB-1 created_by

create or replace function public.force_created_by()
returns trigger
language plpgsql
security invoker
set search_path = ''
as $$
begin
  -- server-side contexts (signup trigger, service role) have no JWT subject: trusted
  if (select auth.uid()) is null then
    return new;
  end if;
  if tg_op = 'INSERT' then
    new.created_by := (select auth.uid());
  elsif tg_op = 'UPDATE' then
    new.created_by := old.created_by;
  end if;
  return new;
end;
$$;

do $$
declare
  t text;
begin
  foreach t in array array['workspaces', 'projects', 'raw_files', 'computation_runs'] loop
    execute format(
      'create trigger %1$s_force_created_by before insert or update on public.%1$I '
      'for each row execute function public.force_created_by()', t);
  end loop;
end;
$$;

-- ------------------------------------------------------------ DB-2 finite numbers
-- abs(NaN) sorts above every number in PostgreSQL and abs(±Infinity) = Infinity, so a
-- magnitude bound rejects all three. 1e12 m is far beyond any surveying quantity.

alter table public.control_points
  add constraint control_points_finite check (
    abs(x) < 1e12 and abs(y) < 1e12 and (z is null or abs(z) < 1e12));
alter table public.setups
  add constraint setups_finite check (abs(instrument_height) < 1e6);
alter table public.observations
  add constraint observations_finite check (
    abs(hz) < 1e6 and (v is null or abs(v) < 1e6) and (sd is null or sd < 1e9)
    and abs(target_height) < 1e6);
alter table public.computed_points
  add constraint computed_points_finite check (
    abs(x) < 1e12 and abs(y) < 1e12 and (z is null or abs(z) < 1e12));

-- ----------------------------------------------------------------- DB-3 size limits

alter table public.profiles
  add constraint profiles_full_name_len check (full_name is null or length(full_name) <= 200);
alter table public.workspaces
  add constraint workspaces_name_len check (length(name) <= 200);
alter table public.projects
  add constraint projects_name_len check (length(name) <= 200),
  add constraint projects_description_len check (description is null or length(description) <= 4000),
  add constraint projects_settings_size check (pg_column_size(settings) <= 65536);
alter table public.control_points
  add constraint control_points_text_len check (
    length(name) <= 200 and (code is null or length(code) <= 200)
    and (note is null or length(note) <= 4000));
alter table public.raw_files
  add constraint raw_files_text_len check (
    length(storage_path) <= 1024 and length(filename) <= 255 and length(format) <= 32
    and (sha256 is null or length(sha256) <= 64)
    and (parser_version is null or length(parser_version) <= 32));
alter table public.setups
  add constraint setups_text_len check (
    length(station) <= 200 and (backsight is null or length(backsight) <= 200)
    and (note is null or length(note) <= 4000));
alter table public.observations
  add constraint observations_text_len check (
    length(target) <= 200 and (code is null or length(code) <= 200));
alter table public.traverses
  add constraint traverses_size check (
    cardinality(route) <= 500 and (name is null or length(name) <= 200));
alter table public.computation_runs
  add constraint computation_runs_size check (
    length(engine_version) <= 32 and length(input_hash) <= 128
    and pg_column_size(settings) <= 65536 and pg_column_size(summary) <= 65536
    and pg_column_size(result) <= 33554432);
alter table public.computed_points
  add constraint computed_points_text_len check (
    length(name) <= 200 and (code is null or length(code) <= 200));

-- the signup trigger must never fail on long metadata: truncate instead
create or replace function public.handle_new_user()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
declare
  display_name text := left(nullif(trim(coalesce(
    new.raw_user_meta_data ->> 'full_name',
    new.raw_user_meta_data ->> 'name',
    ''
  )), ''), 200);
begin
  insert into public.profiles (id, full_name, locale)
  values (
    new.id,
    display_name,
    case when new.raw_user_meta_data ->> 'locale' = 'en' then 'en' else 'el' end
  )
  on conflict (id) do nothing;

  insert into public.workspaces (name, personal, created_by)
  values (
    left(coalesce(display_name, nullif(split_part(coalesce(new.email, ''), '@', 1), ''), 'Workspace'), 200),
    true,
    new.id
  );
  return new;
end;
$$;

-- ------------------------------------------------------------- DB-4 row caps
-- Statement-level triggers (one count per affected project per statement, index-backed).

create or replace function public.enforce_row_caps()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
declare
  cap integer := tg_argv[1]::integer;
  key_col text := tg_argv[0];
  offender record;
begin
  execute format(
    'select k as key, (select count(*) from public.%1$I t where t.%2$I = k) as n '
    'from (select distinct %2$I as k from inserted) d '
    'where (select count(*) from public.%1$I t where t.%2$I = d.k) > $1 limit 1',
    tg_table_name, key_col)
  into offender
  using cap;
  if offender is not null then
    raise exception using
      errcode = 'P0001',
      message = 'row_limit_reached',
      detail = format('%s per %s is limited to %s', tg_table_name, key_col, cap);
  end if;
  return null;
end;
$$;

create trigger observations_row_cap after insert on public.observations
  referencing new table as inserted for each statement
  execute function public.enforce_row_caps('project_id', '500000');
create trigger setups_row_cap after insert on public.setups
  referencing new table as inserted for each statement
  execute function public.enforce_row_caps('project_id', '50000');
create trigger control_points_row_cap after insert on public.control_points
  referencing new table as inserted for each statement
  execute function public.enforce_row_caps('project_id', '100000');
create trigger traverses_row_cap after insert on public.traverses
  referencing new table as inserted for each statement
  execute function public.enforce_row_caps('project_id', '5000');
create trigger raw_files_row_cap after insert on public.raw_files
  referencing new table as inserted for each statement
  execute function public.enforce_row_caps('project_id', '2000');
create trigger computation_runs_row_cap after insert on public.computation_runs
  referencing new table as inserted for each statement
  execute function public.enforce_row_caps('project_id', '1000');
create trigger computed_points_row_cap after insert on public.computed_points
  referencing new table as inserted for each statement
  execute function public.enforce_row_caps('run_id', '250000');

-- --------------------------------------------------- DB-5 team workspaces are paid

create or replace function public.guard_team_workspaces()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
declare
  uid uuid := (select auth.uid());
  owned integer;
begin
  if uid is null or new.personal then
    return new;  -- signup trigger / service role
  end if;
  if public.my_plan() <> 'pro' then
    raise exception using
      errcode = 'P0001',
      message = 'teams_require_pro',
      hint = 'Team workspaces are part of the Pro plan.';
  end if;
  select count(*) into owned
  from public.workspaces w
  where w.created_by = uid and not w.personal;
  if owned >= 20 then
    raise exception using errcode = 'P0001', message = 'workspace_limit_reached';
  end if;
  return new;
end;
$$;

create trigger workspaces_guard_team
  before insert on public.workspaces
  for each row execute function public.guard_team_workspaces();

-- -------------------------------------------- DB-6 save_computation_run validation

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
  v_points jsonb;
begin
  if p_result is null or jsonb_typeof(p_result) <> 'object' then
    raise exception 'p_result must be a JSON object' using errcode = '22023';
  end if;
  if p_settings is not null and jsonb_typeof(p_settings) <> 'object' then
    raise exception 'p_settings must be a JSON object' using errcode = '22023';
  end if;
  if octet_length(p_result::text) > 33554432 then
    raise exception 'computation result too large' using errcode = '54000';
  end if;
  v_points := coalesce(p_result -> 'points', '[]'::jsonb);
  if jsonb_typeof(v_points) <> 'array' then
    raise exception 'p_result.points must be an array' using errcode = '22023';
  end if;
  if jsonb_array_length(v_points) > 250000 then
    raise exception 'too many points in result' using errcode = '54000';
  end if;

  insert into public.computation_runs (project_id, engine_version, input_hash, settings, summary, result)
  values (
    p_project_id,
    left(coalesce(p_result ->> 'engine_version', 'unknown'), 32),
    left(coalesce(p_result ->> 'input_hash', ''), 128),
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
  from jsonb_to_recordset(v_points)
    as p(name text, kind text, code text, x double precision, y double precision, z double precision);

  return v_run_id;
end;
$$;

-- ------------------------------------------------------------------- privileges
-- Trigger functions are not meant to be called directly; RPCs keep their grants.
revoke execute on function public.force_created_by() from public, anon, authenticated;
revoke execute on function public.enforce_row_caps() from public, anon, authenticated;
revoke execute on function public.guard_team_workspaces() from public, anon, authenticated;
revoke execute on function public.handle_new_user() from public, anon, authenticated;
revoke execute on function public.save_computation_run(uuid, jsonb, jsonb) from public, anon;
grant execute on function public.save_computation_run(uuid, jsonb, jsonb) to authenticated, service_role;

-- ------------------------------------------------------- billing webhook ordering
-- Last applied Paddle event time: the webhook ignores stale / replayed deliveries.
alter table public.subscriptions add column last_event_at timestamptz;
