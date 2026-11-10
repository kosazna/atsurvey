-- RLS / RPC / trigger tests. Run with: supabase/tests/run.sh
-- Each check prints "ok - <description>"; the first failure aborts with a non-zero exit.
\set ON_ERROR_STOP on
\set QUIET on
set client_min_messages = notice;
\o /dev/null

-- ---------------------------------------------------------------- tiny test harness
create schema tests;
grant usage on schema tests to anon, authenticated, service_role;

create function tests.ok(cond boolean, description text) returns void
language plpgsql as $$
begin
  if cond is distinct from true then
    raise exception 'not ok - %', description;
  end if;
  raise notice 'ok - %', description;
end;
$$;

-- Expect a statement to fail (optionally with a given SQLSTATE).
create function tests.throws(stmt text, description text, expected_state text default null)
returns void
language plpgsql as $$
begin
  begin
    execute stmt;
  exception when others then
    if expected_state is not null and sqlstate <> expected_state then
      raise exception 'not ok - % (expected %, got %: %)', description, expected_state, sqlstate, sqlerrm;
    end if;
    raise notice 'ok - %', description;
    return;
  end;
  raise exception 'not ok - % (statement succeeded)', description;
end;
$$;

-- Number of rows a statement touched (for silent RLS filtering on update/delete).
create function tests.affected(stmt text) returns integer
language plpgsql as $$
declare
  n integer;
begin
  execute stmt;
  get diagnostics n = row_count;
  return n;
end;
$$;

create function tests.ws_of(uid uuid) returns uuid
language sql security definer stable as $$
  select id from public.workspaces where created_by = uid and personal limit 1;
$$;

create function tests.login(uid uuid) returns void
language sql as $$
  select set_config('request.jwt.claims',
    json_build_object('sub', uid, 'role', 'authenticated')::text, true);
$$;

-- a session that passed two-factor authentication
create function tests.login_aal2(uid uuid) returns void
language sql as $$
  select set_config('request.jwt.claims',
    json_build_object('sub', uid, 'role', 'authenticated', 'aal', 'aal2')::text, true);
$$;

grant execute on all functions in schema tests to anon, authenticated, service_role;

-- user A = 1111..., user B = 2222...
insert into auth.users (id, email, raw_user_meta_data) values
  ('11111111-1111-1111-1111-111111111111', 'a@example.test', '{"full_name": "Alice Surveyor"}'),
  ('22222222-2222-2222-2222-222222222222', 'b@example.test', '{}');

-- ---------------------------------------------------------------- signup trigger
select tests.ok((select count(*) from public.profiles) = 2, 'profiles created for both users');
select tests.ok(
  (select count(*) from public.workspaces where personal) = 2,
  'personal workspace created per user');
select tests.ok(
  (select name from public.workspaces where created_by = '11111111-1111-1111-1111-111111111111') = 'Alice Surveyor',
  'workspace named after full_name');
select tests.ok(
  (select name from public.workspaces where created_by = '22222222-2222-2222-2222-222222222222') = 'b',
  'workspace falls back to email local part');
select tests.ok(
  (select count(*) from public.workspace_members where role = 'owner') = 2,
  'each user owns their personal workspace');
select tests.ok(
  (select locale from public.profiles where id = '11111111-1111-1111-1111-111111111111') = 'el',
  'default locale is el');

-- ---------------------------------------------------------------- user B creates data
begin;
set local role authenticated;
select tests.login('22222222-2222-2222-2222-222222222222');

insert into public.projects (id, workspace_id, name)
values ('bbbbbbbb-0000-0000-0000-000000000001',
        tests.ws_of('22222222-2222-2222-2222-222222222222'), 'B project');
insert into public.control_points (project_id, name, x, y, z)
values ('bbbbbbbb-0000-0000-0000-000000000001', 'K1', 476000, 4210000, 120.5);
insert into public.raw_files (id, project_id, storage_path, filename, format)
values ('bbbbbbbb-0000-0000-0000-0000000000f1', 'bbbbbbbb-0000-0000-0000-000000000001',
        tests.ws_of('22222222-2222-2222-2222-222222222222')::text
          || '/bbbbbbbb-0000-0000-0000-000000000001/f1-z.gsi', 'z.gsi', 'leica_gsi');
insert into public.setups (id, project_id, raw_file_id, station, instrument_height)
values ('bbbbbbbb-0000-0000-0000-0000000000a1', 'bbbbbbbb-0000-0000-0000-000000000001',
        'bbbbbbbb-0000-0000-0000-0000000000f1', 'S1', 1.55);
-- project_id omitted: derived from the setup by trigger
insert into public.observations (setup_id, target, hz, v, sd)
values ('bbbbbbbb-0000-0000-0000-0000000000a1', '101', 1.2, 1.57, 25.3);
insert into public.traverses (project_id, route)
values ('bbbbbbbb-0000-0000-0000-000000000001', array['K0', 'K1', 'S1', 'K2', 'K3']);

select tests.ok(
  (select project_id from public.observations limit 1) = 'bbbbbbbb-0000-0000-0000-000000000001',
  'observation project_id derived from setup');
select tests.ok((select count(*) from public.projects) = 1, 'B sees own project');
select tests.ok((select count(*) from public.workspaces) = 1, 'B sees only own workspace');
insert into storage.objects (bucket_id, name)
values ('raw-files', tests.ws_of('22222222-2222-2222-2222-222222222222')::text
        || '/bbbbbbbb-0000-0000-0000-000000000001/abc-z.gsi');
select tests.ok(true, 'B can upload into own workspace folder');
commit;

-- ---------------------------------------------------------------- user A: isolation
begin;
set local role authenticated;
select tests.login('11111111-1111-1111-1111-111111111111');

select tests.ok((select count(*) from public.workspaces) = 1, 'A sees only own workspace');
select tests.ok((select count(*) from public.projects) = 0, 'A cannot see B projects');
select tests.ok((select count(*) from public.control_points) = 0, 'A cannot see B control points');
select tests.ok((select count(*) from public.setups) = 0, 'A cannot see B setups');
select tests.ok((select count(*) from public.observations) = 0, 'A cannot see B observations');
select tests.ok((select count(*) from public.traverses) = 0, 'A cannot see B traverses');
select tests.ok((select count(*) from public.raw_files) = 0, 'A cannot see B raw files');
select tests.ok((select count(*) from public.workspace_members) = 1, 'A sees only own membership');
select tests.ok((select count(*) from storage.objects) = 0, 'A cannot see B storage objects');

select tests.ok(
  tests.affected($q$update public.control_points set x = 0$q$) = 0,
  'A update of B control points touches 0 rows');
select tests.ok(
  tests.affected($q$delete from public.observations$q$) = 0,
  'A delete of B observations touches 0 rows');
select tests.ok(
  tests.affected($q$update public.projects set name = 'hacked'$q$) = 0,
  'A update of B projects touches 0 rows');

select tests.throws(
  $q$insert into public.control_points (project_id, name, x, y)
     values ('bbbbbbbb-0000-0000-0000-000000000001', 'EVIL', 1, 2)$q$,
  'A cannot insert control point into B project', '42501');
select tests.throws(
  format($q$insert into public.projects (workspace_id, name) values (%L, 'x')$q$,
         tests.ws_of('22222222-2222-2222-2222-222222222222')),
  'A cannot create project in B workspace', '42501');
select tests.throws(
  $q$insert into public.observations (setup_id, target, hz)
     values ('bbbbbbbb-0000-0000-0000-0000000000a1', 'X', 0)$q$,
  'A cannot attach observation to B setup');
select tests.throws(
  format($q$insert into public.workspace_members (workspace_id, user_id, role)
            values (%L, '11111111-1111-1111-1111-111111111111', 'owner')$q$,
         tests.ws_of('22222222-2222-2222-2222-222222222222')),
  'A cannot add self to B workspace', '42501');
select tests.throws(
  format($q$insert into storage.objects (bucket_id, name) values ('raw-files', %L)$q$,
         tests.ws_of('22222222-2222-2222-2222-222222222222')::text || '/p/f.gsi'),
  'A cannot upload into B workspace folder', '42501');
select tests.throws(
  $q$insert into storage.objects (bucket_id, name) values ('raw-files', 'not-a-uuid/f.gsi')$q$,
  'malformed storage path rejected', '42501');
select tests.throws(
  $q$insert into public.workspaces (name, personal, created_by)
     values ('fake personal', true, '11111111-1111-1111-1111-111111111111')$q$,
  'users cannot create personal workspaces', '42501');
select tests.ok(
  tests.affected(format($q$delete from public.workspaces where id = %L$q$,
                        tests.ws_of('11111111-1111-1111-1111-111111111111'))) = 0,
  'personal workspace cannot be deleted');
commit;

-- ---------------------------------------------------------------- composite FK: raw file in another project
begin;
set local role authenticated;
select tests.login('11111111-1111-1111-1111-111111111111');
insert into public.projects (id, workspace_id, name)
values ('aaaaaaaa-0000-0000-0000-000000000001',
        tests.ws_of('11111111-1111-1111-1111-111111111111'), 'A project 1');
select tests.throws(
  $q$insert into public.setups (project_id, raw_file_id, station)
     values ('aaaaaaaa-0000-0000-0000-000000000001', 'bbbbbbbb-0000-0000-0000-0000000000f1', 'S')$q$,
  'setup cannot reference raw file of another project', '23503');
commit;

-- ---------------------------------------------------------------- free-plan limit
begin;
set local role authenticated;
select tests.login('11111111-1111-1111-1111-111111111111');
select tests.ok(public.workspace_plan(tests.ws_of('11111111-1111-1111-1111-111111111111')) = 'free',
  'A is on the free plan');
insert into public.projects (id, workspace_id, name) values
  ('aaaaaaaa-0000-0000-0000-000000000002', tests.ws_of('11111111-1111-1111-1111-111111111111'), 'A project 2'),
  ('aaaaaaaa-0000-0000-0000-000000000003', tests.ws_of('11111111-1111-1111-1111-111111111111'), 'A project 3');
select tests.ok((select count(*) from public.projects) = 3, 'free plan allows 3 projects');
select tests.throws(
  format($q$insert into public.projects (workspace_id, name) values (%L, 'A project 4')$q$,
         tests.ws_of('11111111-1111-1111-1111-111111111111')),
  'free plan blocks a 4th active project', 'P0001');
update public.projects set archived_at = now() where id = 'aaaaaaaa-0000-0000-0000-000000000003';
insert into public.projects (id, workspace_id, name) values
  ('aaaaaaaa-0000-0000-0000-000000000004', tests.ws_of('11111111-1111-1111-1111-111111111111'), 'A project 4');
select tests.ok(true, 'archiving frees a slot');
select tests.throws(
  $q$update public.projects set archived_at = null where id = 'aaaaaaaa-0000-0000-0000-000000000003'$q$,
  'unarchiving past the limit is blocked', 'P0001');
commit;

-- ---------------------------------------------------------------- subscriptions
begin;
set local role authenticated;
select tests.login('11111111-1111-1111-1111-111111111111');
select tests.throws(
  format($q$insert into public.subscriptions (workspace_id, plan, status) values (%L, 'pro', 'active')$q$,
         tests.ws_of('11111111-1111-1111-1111-111111111111')),
  'authenticated users cannot write subscriptions', '42501');
select tests.throws(
  $q$update public.subscriptions set plan = 'pro'$q$,
  'authenticated users cannot update subscriptions', '42501');
commit;

begin;
set local role service_role;
insert into public.subscriptions (workspace_id, plan, status, current_period_end)
values (tests.ws_of('11111111-1111-1111-1111-111111111111'), 'pro', 'active', now() + interval '30 days');
select tests.ok(true, 'service_role can write subscriptions');
commit;

begin;
set local role authenticated;
select tests.login('11111111-1111-1111-1111-111111111111');
select tests.ok(public.workspace_plan(tests.ws_of('11111111-1111-1111-1111-111111111111')) = 'pro',
  'active subscription => pro plan');
select tests.ok((select count(*) from public.subscriptions) = 1, 'member can read own subscription');
select tests.ok(public.my_plan() = 'pro', 'my_plan => pro for subscribed member');
insert into public.projects (workspace_id, name)
values (tests.ws_of('11111111-1111-1111-1111-111111111111'), 'A project 5');
select tests.ok(true, 'pro plan lifts the project limit');
commit;

begin;
set local role authenticated;
select tests.login('22222222-2222-2222-2222-222222222222');
select tests.ok((select count(*) from public.subscriptions) = 0, 'B cannot read A subscription');
select tests.ok(public.my_plan() = 'free', 'my_plan => free for B');
select tests.ok(public.workspace_plan(tests.ws_of('11111111-1111-1111-1111-111111111111')) = 'free',
  'workspace_plan reveals nothing about foreign workspaces');
commit;

-- ---------------------------------------------------------------- save_computation_run
begin;
set local role authenticated;
select tests.login('11111111-1111-1111-1111-111111111111');
select public.save_computation_run(
  'aaaaaaaa-0000-0000-0000-000000000001',
  $j${
    "engine_version": "0.1.0",
    "input_hash": "abc123",
    "summary": {"n_control": 1, "n_detail_points": 1},
    "points": [
      {"name": "K1", "x": 476000.123, "y": 4210000.456, "z": 120.5, "kind": "control", "code": null},
      {"name": "101", "x": 476010.0, "y": 4210020.0, "z": null, "kind": "detail", "code": "TREE"}
    ]
  }$j$::jsonb,
  '{"reduction": {"scale_mode": "leg_simpson"}}'::jsonb
) as run_id \gset
select tests.ok(:'run_id' is not null, 'save_computation_run returns a run id');
select tests.ok(
  (select count(*) from public.computed_points where run_id = :'run_id') = 2,
  'computed points inserted');
select tests.ok(
  (select bool_and(extensions.st_srid(geom) = 2100) from public.computed_points where run_id = :'run_id'),
  'computed point geometry SRID is 2100');
select tests.ok(
  (select extensions.st_z(geom) = 120.5 and abs(extensions.st_x(geom) - 476000.123) < 1e-9
   from public.computed_points where run_id = :'run_id' and name = 'K1'),
  'computed point geometry carries x/y/z');
select tests.ok(
  (select extensions.st_z(geom) = 0 and z is null
   from public.computed_points where run_id = :'run_id' and name = '101'),
  'null height stored as z=0 in geometry, null in column');
select tests.ok(
  (select engine_version = '0.1.0' and input_hash = 'abc123' and summary ->> 'n_control' = '1'
          and settings -> 'reduction' ->> 'scale_mode' = 'leg_simpson'
   from public.computation_runs where id = :'run_id'),
  'run metadata stored');
select tests.throws(
  $q$select public.save_computation_run('bbbbbbbb-0000-0000-0000-000000000001',
       '{"engine_version":"x","input_hash":"y","points":[]}'::jsonb, '{}'::jsonb)$q$,
  'cannot save a run into a foreign project', '42501');
select tests.throws(
  format($q$update public.computation_runs set input_hash = 'tampered' where id = %L$q$, :'run_id'),
  'computation runs are immutable', '42501');
commit;

begin;
set local role authenticated;
select tests.login('22222222-2222-2222-2222-222222222222');
select tests.ok((select count(*) from public.computation_runs) = 0, 'B cannot see A runs');
select tests.ok((select count(*) from public.computed_points) = 0, 'B cannot see A computed points');
commit;

-- ---------------------------------------------------------------- cascade delete
begin;
set local role authenticated;
select tests.login('11111111-1111-1111-1111-111111111111');
delete from public.projects where id = 'aaaaaaaa-0000-0000-0000-000000000001';
select tests.ok((select count(*) from public.computation_runs) = 0, 'deleting a project cascades to runs');
select tests.ok((select count(*) from public.computed_points) = 0, 'deleting a project cascades to points');
commit;

-- ---------------------------------------------------------------- anon
begin;
set local role anon;
select tests.throws($q$select count(*) from public.projects$q$, 'anon has no table access', '42501');
select tests.throws(
  $q$select public.save_computation_run(gen_random_uuid(), '{}'::jsonb, '{}'::jsonb)$q$,
  'anon cannot call RPCs', '42501');
commit;

-- ---------------------------------------------------------------- membership guards
begin;
set local role authenticated;
select tests.login('11111111-1111-1111-1111-111111111111');
select tests.throws(
  $q$delete from public.workspace_members where user_id = '11111111-1111-1111-1111-111111111111'$q$,
  'owner cannot leave their personal workspace', '42501');
commit;

begin;
-- a team workspace owned by A with B as admin
set local role authenticated;
select tests.login('11111111-1111-1111-1111-111111111111');
insert into public.workspaces (id, name, personal, created_by)
values ('cccccccc-0000-0000-0000-000000000001', 'Team', false, '11111111-1111-1111-1111-111111111111');
select tests.throws(
  $q$insert into public.workspace_members (workspace_id, user_id, role)
     values ('cccccccc-0000-0000-0000-000000000001', '22222222-2222-2222-2222-222222222222', 'admin')$q$,
  'owners cannot add members directly (invitation and consent only)', '42501');
commit;
-- B joins through the invitation tests below; set up here directly (as the database owner)
insert into public.workspace_members (workspace_id, user_id, role)
values ('cccccccc-0000-0000-0000-000000000001', '22222222-2222-2222-2222-222222222222', 'admin');

begin;
set local role authenticated;
select tests.login('22222222-2222-2222-2222-222222222222');
select tests.throws(
  $q$update public.workspace_members set role = 'owner'
     where workspace_id = 'cccccccc-0000-0000-0000-000000000001'
       and user_id = '22222222-2222-2222-2222-222222222222'$q$,
  'admin cannot promote themselves to owner', '42501');
select tests.throws(
  $q$update public.workspace_members set role = 'member'
     where workspace_id = 'cccccccc-0000-0000-0000-000000000001'
       and user_id = '11111111-1111-1111-1111-111111111111'$q$,
  'admin cannot demote the owner', '42501');
commit;

begin;
set local role authenticated;
select tests.login('11111111-1111-1111-1111-111111111111');
select tests.throws(
  $q$update public.workspace_members set role = 'admin'
     where workspace_id = 'cccccccc-0000-0000-0000-000000000001'
       and user_id = '11111111-1111-1111-1111-111111111111'$q$,
  'the last owner cannot step down', '42501');
commit;

-- ---------------------------------------------------------------- security hardening (2026-11-10)
begin;
set local role authenticated;
select tests.login('22222222-2222-2222-2222-222222222222');
select tests.throws(
  $q$insert into public.workspaces (name, personal) values ('B team', false)$q$,
  'free users cannot create team workspaces (project-limit bypass)', 'P0001');
-- created_by cannot be spoofed
insert into public.projects (id, workspace_id, name, created_by)
values ('bbbbbbbb-0000-0000-0000-0000000000c7',
        tests.ws_of('22222222-2222-2222-2222-222222222222'), 'B spoof',
        '11111111-1111-1111-1111-111111111111');
select tests.ok(
  (select created_by from public.projects where id = 'bbbbbbbb-0000-0000-0000-0000000000c7')
    = '22222222-2222-2222-2222-222222222222',
  'created_by is forced to the caller on insert');
update public.projects set created_by = '11111111-1111-1111-1111-111111111111'
where id = 'bbbbbbbb-0000-0000-0000-0000000000c7';
select tests.ok(
  (select created_by from public.projects where id = 'bbbbbbbb-0000-0000-0000-0000000000c7')
    = '22222222-2222-2222-2222-222222222222',
  'created_by is immutable on update');
select tests.throws(
  $q$insert into public.control_points (project_id, name, x, y)
     values ('bbbbbbbb-0000-0000-0000-000000000001', 'NAN', 'NaN', 1)$q$,
  'NaN coordinates rejected', '23514');
select tests.throws(
  $q$insert into public.control_points (project_id, name, x, y)
     values ('bbbbbbbb-0000-0000-0000-000000000001', 'INF', 'Infinity', 1)$q$,
  'infinite coordinates rejected', '23514');
select tests.throws(
  $q$insert into public.observations (setup_id, target, hz) values
     ('bbbbbbbb-0000-0000-0000-0000000000a1', repeat('x', 201), 0)$q$,
  'oversized point names rejected', '23514');
select tests.throws(
  $q$update public.projects set settings = jsonb_build_object('blob', repeat(md5(random()::text), 5000))
     where id = 'bbbbbbbb-0000-0000-0000-000000000001'$q$,
  'oversized project settings rejected', '23514');
select tests.throws(
  $q$select public.save_computation_run('bbbbbbbb-0000-0000-0000-000000000001',
       '{"points": {"not": "an array"}}'::jsonb, '{}'::jsonb)$q$,
  'save_computation_run rejects malformed points', '22023');
select tests.throws(
  $q$select public.save_computation_run('bbbbbbbb-0000-0000-0000-000000000001',
       '{"points": [{"name": "P", "kind": "detail", "x": 1e15, "y": 1}]}'::jsonb, '{}'::jsonb)$q$,
  'save_computation_run rejects absurd coordinates', '23514');
select tests.throws(
  $q$select public.save_computation_run('bbbbbbbb-0000-0000-0000-000000000001',
       '{}'::jsonb, '[1]'::jsonb)$q$,
  'save_computation_run rejects non-object settings', '22023');
select tests.throws(
  $q$insert into public.computation_runs (project_id, engine_version, input_hash, result)
     select 'bbbbbbbb-0000-0000-0000-000000000001', '0', 'h', '{}'::jsonb
     from generate_series(1, 1001)$q$,
  'row cap: at most 1000 runs per project', 'P0001');
select tests.ok(
  (select count(*) from public.computation_runs
   where project_id = 'bbbbbbbb-0000-0000-0000-000000000001' and engine_version = '0') = 0,
  'row cap rolls back the whole statement');
commit;

-- signup with hostile metadata must still succeed (values are truncated)
insert into auth.users (id, email, raw_user_meta_data) values
  ('33333333-3333-3333-3333-333333333333', 'c@example.test',
   jsonb_build_object('full_name', repeat('Ω', 5000), 'locale', 'xx'));
select tests.ok(
  (select length(name) from public.workspaces
   where created_by = '33333333-3333-3333-3333-333333333333') = 200,
  'signup truncates oversized display names');
select tests.ok(
  (select locale from public.profiles where id = '33333333-3333-3333-3333-333333333333') = 'el',
  'signup ignores unknown locales');

-- ================================================================ isolation (2026-11-11)
-- Team 'cccc…0001': A owner, B admin (above); D member and V viewer join here.
insert into auth.users (id, email) values
  ('44444444-4444-4444-4444-444444444444', 'd@example.test'),
  ('55555555-5555-5555-5555-555555555555', 'v@example.test');
insert into public.workspace_members (workspace_id, user_id, role) values
  ('cccccccc-0000-0000-0000-000000000001', '44444444-4444-4444-4444-444444444444', 'member'),
  ('cccccccc-0000-0000-0000-000000000001', '55555555-5555-5555-5555-555555555555', 'viewer');

begin;
set local role authenticated;
select tests.login('11111111-1111-1111-1111-111111111111');
insert into public.projects (id, workspace_id, name)
values ('cccccccc-0000-0000-0000-000000000101', 'cccccccc-0000-0000-0000-000000000001', 'Team project');
commit;

-- ---------------------------------------------------------------- viewer is read-only (DB-7)
begin;
set local role authenticated;
select tests.login('55555555-5555-5555-5555-555555555555');
select tests.ok(
  (select count(*) from public.projects where id = 'cccccccc-0000-0000-0000-000000000101') = 1,
  'viewer sees team projects');
select tests.throws(
  $q$insert into public.control_points (project_id, name, x, y)
     values ('cccccccc-0000-0000-0000-000000000101', 'V1', 1, 1)$q$,
  'viewer cannot add points', '42501');
select tests.ok(
  tests.affected($q$update public.projects set name = 'hacked'
                    where id = 'cccccccc-0000-0000-0000-000000000101'$q$) = 0,
  'viewer cannot rename a project');
select tests.throws(
  $q$insert into public.projects (workspace_id, name)
     values ('cccccccc-0000-0000-0000-000000000001', 'V project')$q$,
  'viewer cannot create projects', '42501');
select tests.throws(
  $q$select public.save_computation_run('cccccccc-0000-0000-0000-000000000101',
       '{"points":[]}'::jsonb, '{}'::jsonb)$q$,
  'viewer cannot save runs', '42501');
select tests.throws(
  $q$insert into storage.objects (bucket_id, name) values ('raw-files',
     'cccccccc-0000-0000-0000-000000000001/cccccccc-0000-0000-0000-000000000101/v.gsi')$q$,
  'viewer cannot upload files', '42501');
select tests.ok((select count(*) from public.audit_events
                 where workspace_id = 'cccccccc-0000-0000-0000-000000000001') = 0,
  'viewer cannot read the team audit log');
commit;

-- ---------------------------------------------------------------- member limits (DB-8, DB-9)
begin;
set local role authenticated;
select tests.login('44444444-4444-4444-4444-444444444444');
insert into public.control_points (project_id, name, x, y)
values ('cccccccc-0000-0000-0000-000000000101', 'D1', 476000, 4210000);
select tests.ok(true, 'member can edit team project data');
insert into storage.objects (bucket_id, name) values ('raw-files',
  'cccccccc-0000-0000-0000-000000000001/cccccccc-0000-0000-0000-000000000101/f-team.gsi');
insert into public.raw_files (id, project_id, storage_path, filename, format)
values ('cccccccc-0000-0000-0000-0000000001f1', 'cccccccc-0000-0000-0000-000000000101',
        'cccccccc-0000-0000-0000-000000000001/cccccccc-0000-0000-0000-000000000101/f-team.gsi',
        'team.gsi', 'leica_gsi');
select tests.ok(true, 'member can upload files into the team project');
select tests.throws(
  format($q$insert into storage.objects (bucket_id, name) values ('raw-files', %L)$q$,
    tests.ws_of('44444444-4444-4444-4444-444444444444')::text
      || '/cccccccc-0000-0000-0000-000000000101/f-wrong-ws.gsi'),
  'upload path must name the project''s own workspace', '42501');
select tests.throws(
  format($q$insert into public.raw_files (project_id, storage_path, filename, format)
     values ('cccccccc-0000-0000-0000-000000000101', %L, 'x.gsi', 'leica_gsi')$q$,
    tests.ws_of('22222222-2222-2222-2222-222222222222')::text
      || '/bbbbbbbb-0000-0000-0000-000000000001/f1-z.gsi'),
  'a raw file row cannot point at another project''s object', '23514');
select tests.ok(
  tests.affected($q$delete from public.projects where id = 'cccccccc-0000-0000-0000-000000000101'$q$) = 0,
  'member cannot delete a team project');
select tests.throws(
  format($q$update public.projects set workspace_id = %L
            where id = 'cccccccc-0000-0000-0000-000000000101'$q$,
    tests.ws_of('44444444-4444-4444-4444-444444444444')),
  'member cannot move a team project into their own workspace', '42501');
select public.log_export('cccccccc-0000-0000-0000-000000000101', 'pdf');
select tests.throws(
  $q$select public.log_export('cccccccc-0000-0000-0000-000000000101', 'pdf; drop')$q$,
  'log_export rejects malformed formats', '22023');
select tests.ok((select count(*) from public.audit_events
                 where workspace_id = 'cccccccc-0000-0000-0000-000000000001') = 0,
  'member cannot read the team audit log');
commit;

begin;
set local role authenticated;
select tests.login('33333333-3333-3333-3333-333333333333');
select tests.throws(
  $q$select public.log_export('cccccccc-0000-0000-0000-000000000101', 'pdf')$q$,
  'outsiders cannot log exports of a foreign project', '42501');
commit;

-- ---------------------------------------------------------------- audit log (DB-10)
begin;
set local role authenticated;
select tests.login('11111111-1111-1111-1111-111111111111');
select tests.ok(
  (select array_agg(distinct action order by action) from public.audit_events
   where workspace_id = 'cccccccc-0000-0000-0000-000000000001')
  @> array['file.uploaded', 'member.added', 'project.created', 'project.exported', 'workspace.created'],
  'owner reads team events: created, member added, file uploaded, exported');
select tests.ok(
  (select actor from public.audit_events where action = 'project.exported')
    = '44444444-4444-4444-4444-444444444444',
  'audit events record the actor');
select tests.ok(
  not exists (select 1 from public.audit_events
              where workspace_id = tests.ws_of('22222222-2222-2222-2222-222222222222')),
  'owner cannot read events of a workspace they do not own');
select tests.throws($q$update public.audit_events set action = 'x.y'$q$,
  'audit events cannot be edited', '42501');
select tests.throws($q$delete from public.audit_events$q$,
  'audit events cannot be deleted', '42501');
select tests.throws(
  $q$insert into public.audit_events (workspace_id, action)
     values ('cccccccc-0000-0000-0000-000000000001', 'fake.event')$q$,
  'audit events cannot be forged', '42501');
commit;

begin;
set local role service_role;
select tests.throws($q$update public.audit_events set action = 'x.y'$q$,
  'not even service_role can edit audit events', '42501');
select tests.throws($q$delete from public.audit_events$q$,
  'not even service_role can delete audit events', '42501');
commit;

-- ---------------------------------------------------------------- moves follow the project (DB-8/9)
begin;
set local role authenticated;
select tests.login('22222222-2222-2222-2222-222222222222');  -- B: team admin, owns personal
update public.projects set workspace_id = tests.ws_of('22222222-2222-2222-2222-222222222222')
where id = 'cccccccc-0000-0000-0000-000000000101';
select tests.ok(
  (select workspace_id from public.projects where id = 'cccccccc-0000-0000-0000-000000000101')
    = tests.ws_of('22222222-2222-2222-2222-222222222222'),
  'admin can move a project between workspaces they administer');
select tests.ok(
  (select count(*) from storage.objects where name like '%/cccccccc-0000-0000-0000-000000000101/%') = 1,
  'moved project''s files stay readable by its new workspace');
commit;

begin;
set local role authenticated;
select tests.login('55555555-5555-5555-5555-555555555555');
select tests.ok(
  (select count(*) from storage.objects where name like '%/cccccccc-0000-0000-0000-000000000101/%') = 0,
  'moved project''s files are no longer readable by the old workspace');
commit;

select tests.ok(
  (select count(*) from public.audit_events
   where project_id = 'cccccccc-0000-0000-0000-000000000101'
     and action in ('project.moved_out', 'project.moved_in')) = 2,
  'a move is recorded in both workspaces');

-- ---------------------------------------------------------------- storage cleanup (DB-11)
begin;
set local role authenticated;
select tests.login('22222222-2222-2222-2222-222222222222');
delete from public.projects where id = 'cccccccc-0000-0000-0000-000000000101';
select tests.throws($q$select count(*) from public.storage_deletions$q$,
  'users cannot read the storage deletion queue', '42501');
select tests.throws($q$select public.storage_orphans()$q$,
  'users cannot list storage orphans', '42501');
commit;
select tests.ok(
  exists (select 1 from public.storage_deletions
          where name = 'cccccccc-0000-0000-0000-000000000001/cccccccc-0000-0000-0000-000000000101/f-team.gsi'),
  'deleting a project queues its stored files for removal');
-- an object another row still references must not be deleted
insert into public.storage_deletions (bucket_id, name)
select 'raw-files', storage_path from public.raw_files where id = 'bbbbbbbb-0000-0000-0000-0000000000f1';
begin;
set local role service_role;
create temporary table claimed on commit drop as select * from public.claim_storage_deletions(100);
select tests.ok(
  exists (select 1 from claimed where name like '%/f-team.gsi')
  and not exists (select 1 from claimed where name like '%/f1-z.gsi'),
  'janitor claims unreferenced objects and skips ones still referenced');
commit;
select tests.ok(
  exists (select 1 from public.audit_events where action = 'project.deleted'
          and project_id = 'cccccccc-0000-0000-0000-000000000101'),
  'project deletion is audited');
select tests.ok(
  not exists (select 1 from public.audit_events where action = 'file.deleted'
              and project_id = 'cccccccc-0000-0000-0000-000000000101'),
  'cascaded child deletes do not flood the audit log');
select tests.ok(
  (select allowed_mime_types from storage.buckets where id = 'raw-files') @> array['text/plain']
  and not ((select allowed_mime_types from storage.buckets where id = 'raw-files') && array['text/html', 'image/svg+xml']),
  'raw-files bucket accepts survey file types only');

-- ---------------------------------------------------------------- account deletion (DB-12)
begin;
set local role authenticated;
select tests.login('11111111-1111-1111-1111-111111111111');
select tests.ok(
  (select count(*) from public.my_account_deletion_blockers()) = 1,
  'sole team owner sees the team as a deletion blocker');
select tests.throws(
  $q$select public.delete_account_data('33333333-3333-3333-3333-333333333333')$q$,
  'users cannot call delete_account_data', '42501');
commit;

begin;
set local role service_role;
select tests.throws(
  $q$select public.delete_account_data('11111111-1111-1111-1111-111111111111')$q$,
  'account deletion refused while the user alone owns a team with members', 'P0001');
select tests.ok(
  public.delete_account_data('33333333-3333-3333-3333-333333333333') = 1,
  'account deletion removes the personal workspace');
commit;
select tests.ok(
  not exists (select 1 from public.workspace_members where user_id = '33333333-3333-3333-3333-333333333333'),
  'no memberships remain for the deleted account');
delete from auth.users where id = '33333333-3333-3333-3333-333333333333';
select tests.ok(
  not exists (select 1 from public.profiles where id = '33333333-3333-3333-3333-333333333333'),
  'deleting the auth user removes the profile');

insert into public.workspaces (id, name, personal) values
  ('dddddddd-0000-0000-0000-000000000001', 'Orphan', false);
begin;
set local role service_role;
select tests.ok(public.purge_memberless_workspaces() >= 1, 'memberless workspaces are purged');
commit;
select tests.ok(
  not exists (select 1 from public.workspaces where id = 'dddddddd-0000-0000-0000-000000000001'),
  'orphan workspace is gone');

-- ================================================================ two-factor (DB-14)
insert into auth.users (id, email) values ('66666666-6666-6666-6666-666666666666', 'm@example.test');
insert into auth.mfa_factors (user_id, status) values ('66666666-6666-6666-6666-666666666666', 'verified');

begin;
set local role authenticated;
select tests.login_aal2('66666666-6666-6666-6666-666666666666');
insert into public.projects (id, workspace_id, name)
values ('66666666-0000-0000-0000-000000000001', tests.ws_of('66666666-6666-6666-6666-666666666666'), 'M project');
select tests.ok((select count(*) from public.projects) = 1, 'two-factor user works normally from an aal2 session');
commit;

begin;
set local role authenticated;
select tests.login('66666666-6666-6666-6666-666666666666');
select tests.ok((select count(*) from public.projects) = 0,
  'a password-only session of a two-factor user sees no projects');
select tests.ok((select count(*) from public.workspaces) = 0,
  'a password-only session of a two-factor user sees no workspaces');
select tests.throws(
  format($q$insert into public.projects (workspace_id, name) values (%L, 'stolen')$q$,
    tests.ws_of('66666666-6666-6666-6666-666666666666')),
  'a password-only session of a two-factor user cannot write', '42501');
commit;

-- team requires two-factor
begin;
set local role authenticated;
select tests.login('11111111-1111-1111-1111-111111111111');
select tests.throws(
  $q$update public.workspaces set require_mfa = true where id = 'cccccccc-0000-0000-0000-000000000001'$q$,
  'require_mfa cannot be switched on without a two-factor session', '42501');
commit;

begin;
set local role authenticated;
select tests.login_aal2('22222222-2222-2222-2222-222222222222');
select tests.throws(
  $q$update public.workspaces set require_mfa = true where id = 'cccccccc-0000-0000-0000-000000000001'$q$,
  'an admin cannot switch require_mfa', '42501');
commit;

begin;
set local role authenticated;
select tests.login_aal2('11111111-1111-1111-1111-111111111111');
update public.workspaces set require_mfa = true where id = 'cccccccc-0000-0000-0000-000000000001';
insert into public.projects (id, workspace_id, name)
values ('cccccccc-0000-0000-0000-000000000201', 'cccccccc-0000-0000-0000-000000000001', 'MFA team project');
select tests.ok(
  exists (select 1 from public.audit_events where action = 'workspace.mfa_required'
          and workspace_id = 'cccccccc-0000-0000-0000-000000000001'),
  'owner switches require_mfa on from an aal2 session (audited)');
commit;

begin;
set local role authenticated;
select tests.login('44444444-4444-4444-4444-444444444444');
select tests.ok(
  (select count(*) from public.projects where workspace_id = 'cccccccc-0000-0000-0000-000000000001') = 0,
  'members without two-factor are locked out of a workspace that requires it');
select tests.ok(
  (select count(*) from public.projects where workspace_id = tests.ws_of('44444444-4444-4444-4444-444444444444')) >= 0
  and (select count(*) from public.workspaces where id = tests.ws_of('44444444-4444-4444-4444-444444444444')) = 1,
  'the same member still reaches their own personal workspace');
commit;

begin;
set local role authenticated;
select tests.login_aal2('44444444-4444-4444-4444-444444444444');
select tests.ok(
  (select count(*) from public.projects where workspace_id = 'cccccccc-0000-0000-0000-000000000001') = 1,
  'with a two-factor session the member is back in');
commit;

-- ================================================================ invitations (DB-15)
insert into public.subscriptions (workspace_id, plan, status)
values ('cccccccc-0000-0000-0000-000000000001', 'pro', 'active');
insert into auth.users (id, email, email_confirmed_at) values
  ('77777777-7777-7777-7777-777777777777', 'e@example.test', now()),
  ('88888888-8888-8888-8888-888888888888', 'u@example.test', null),
  ('99999999-9999-9999-9999-999999999999', 'f@example.test', now());

begin;
set local role authenticated;
select tests.login_aal2('11111111-1111-1111-1111-111111111111');
select public.invite_member('cccccccc-0000-0000-0000-000000000001', 'e@example.test', 'viewer');
select set_config('tests.inv_e', public.invite_member('cccccccc-0000-0000-0000-000000000001', '  E@Example.TEST ', 'member')::text, false);
select public.invite_member('cccccccc-0000-0000-0000-000000000001', 'u@example.test', 'member');
select public.invite_member('cccccccc-0000-0000-0000-000000000001', 'f@example.test', 'member');
select tests.ok(
  (select count(*) from public.workspace_invitations
   where email = 'e@example.test' and revoked_at is null and accepted_at is null) = 1,
  'a new invitation replaces the pending one for the same (normalised) e-mail');
select tests.throws(
  $q$select public.invite_member('cccccccc-0000-0000-0000-000000000001', 'x@example.test', 'owner')$q$,
  'nobody is invited as owner', '22023');
select tests.throws(
  $q$select public.invite_member('cccccccc-0000-0000-0000-000000000001', 'not-an-email', 'member')$q$,
  'malformed e-mails are rejected', '22023');
select tests.throws(
  $q$select public.invite_member('cccccccc-0000-0000-0000-000000000001', 'd@example.test', 'member')$q$,
  'existing members are not invited again', 'P0001');
select tests.throws(
  format($q$select public.invite_member(%L, 'x@example.test', 'member')$q$,
    tests.ws_of('11111111-1111-1111-1111-111111111111')),
  'personal workspaces take no invitations', 'P0001');
select tests.throws(
  $q$insert into public.workspace_invitations (workspace_id, email, role)
     values ('cccccccc-0000-0000-0000-000000000001', 'y@example.test', 'member')$q$,
  'invitations cannot be inserted directly', '42501');
select tests.ok((select count(*) from public.workspace_invitations) >= 4, 'owner sees the team invitations');
commit;

begin;
set local role authenticated;
select tests.login_aal2('22222222-2222-2222-2222-222222222222');
select tests.throws(
  $q$select public.invite_member('cccccccc-0000-0000-0000-000000000001', 'x@example.test', 'admin')$q$,
  'only owners invite admins', '42501');
select public.invite_member('cccccccc-0000-0000-0000-000000000001', 'viewer2@example.test', 'viewer');
select tests.ok(true, 'admins invite members and viewers');
commit;

begin;
set local role authenticated;
select tests.login_aal2('44444444-4444-4444-4444-444444444444');
select tests.throws(
  $q$select public.invite_member('cccccccc-0000-0000-0000-000000000001', 'x@example.test', 'member')$q$,
  'members cannot invite', '42501');
select tests.ok((select count(*) from public.workspace_invitations) = 0, 'members cannot see invitations');
select tests.throws(
  format($q$select public.revoke_invitation(%L)$q$, current_setting('tests.inv_e')),
  'members cannot revoke invitations', '42501');
commit;

-- the invitee, and only the invitee, sees and answers it
begin;
set local role authenticated;
select tests.login('55555555-5555-5555-5555-555555555555');
select tests.ok((select count(*) from public.my_invitations()) = 0, 'others do not see the invitation');
select tests.throws(
  format($q$select public.accept_invitation(%L)$q$, current_setting('tests.inv_e')),
  'others cannot accept it', 'P0001');
commit;

begin;
set local role authenticated;
select tests.login('88888888-8888-8888-8888-888888888888');
select tests.ok((select count(*) from public.my_invitations()) = 0,
  'an unconfirmed e-mail sees no invitations');
commit;

begin;
set local role authenticated;
select tests.login('77777777-7777-7777-7777-777777777777');
select tests.ok(
  (select count(*) from public.my_invitations() where workspace_name = 'Team' and role = 'member') = 1,
  'the invitee sees the invitation with workspace and role');
select public.accept_invitation(current_setting('tests.inv_e')::uuid);
select tests.throws(
  format($q$select public.accept_invitation(%L)$q$, current_setting('tests.inv_e')),
  'an invitation is accepted once', 'P0001');
commit;
select tests.ok(
  exists (select 1 from public.workspace_members where user_id = '77777777-7777-7777-7777-777777777777'
          and workspace_id = 'cccccccc-0000-0000-0000-000000000001' and role = 'member'),
  'accepting adds the member with the invited role');

begin;
set local role authenticated;
select tests.login('99999999-9999-9999-9999-999999999999');
select public.decline_invitation((select id from public.my_invitations() limit 1));
select tests.ok((select count(*) from public.my_invitations()) = 0, 'a declined invitation disappears');
commit;

-- roster: members only (the team requires two-factor, so aal2)
begin;
set local role authenticated;
select tests.login_aal2('77777777-7777-7777-7777-777777777777');
select tests.ok(
  (select count(*) from public.workspace_roster('cccccccc-0000-0000-0000-000000000001')
   where email = 'a@example.test' and role = 'owner') = 1,
  'members see fellow members with e-mail and role');
select tests.ok(
  (select role from public.my_workspaces() where id = 'cccccccc-0000-0000-0000-000000000001') = 'member'
  and (select plan from public.my_workspaces() where id = 'cccccccc-0000-0000-0000-000000000001') = 'pro',
  'my_workspaces lists role and plan');
commit;

begin;
set local role authenticated;
select tests.login('77777777-7777-7777-7777-777777777777');
select tests.throws(
  $q$select * from public.workspace_roster('cccccccc-0000-0000-0000-000000000001')$q$,
  'the roster obeys the team two-factor requirement', '42501');
commit;

begin;
set local role authenticated;
select tests.login_aal2('66666666-6666-6666-6666-666666666666');
select tests.throws(
  $q$select * from public.workspace_roster('cccccccc-0000-0000-0000-000000000001')$q$,
  'outsiders cannot read a roster', '42501');
commit;

-- ownership transfer
begin;
set local role authenticated;
select tests.login_aal2('11111111-1111-1111-1111-111111111111');
select public.transfer_ownership('cccccccc-0000-0000-0000-000000000001', '22222222-2222-2222-2222-222222222222');
select tests.ok(
  (select role from public.workspace_members where user_id = '22222222-2222-2222-2222-222222222222'
     and workspace_id = 'cccccccc-0000-0000-0000-000000000001') = 'owner'
  and (select role from public.workspace_members where user_id = '11111111-1111-1111-1111-111111111111'
     and workspace_id = 'cccccccc-0000-0000-0000-000000000001') = 'admin',
  'ownership transfer swaps owner and admin atomically');
select tests.throws(
  $q$select public.transfer_ownership('cccccccc-0000-0000-0000-000000000001', '11111111-1111-1111-1111-111111111111')$q$,
  'a former owner cannot transfer again', '42501');
commit;

begin;
set local role authenticated;
select tests.login_aal2('22222222-2222-2222-2222-222222222222');
select public.transfer_ownership('cccccccc-0000-0000-0000-000000000001', '11111111-1111-1111-1111-111111111111');
select tests.ok(
  exists (select 1 from public.audit_events where action = 'member.role_changed'
          and workspace_id = 'cccccccc-0000-0000-0000-000000000001'),
  'role changes from a transfer are audited');
commit;

-- ---------------------------------------------------------------- RLS enabled everywhere
select tests.ok(
  not exists (
    select 1 from pg_class c join pg_namespace n on n.oid = c.relnamespace
    where n.nspname = 'public' and c.relkind = 'r' and not c.relrowsecurity
      and c.relname <> 'spatial_ref_sys'
  ),
  'RLS enabled on every public table');

\echo 'ALL TESTS PASSED'
