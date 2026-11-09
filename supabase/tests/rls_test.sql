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
        'x/y/z.gsi', 'z.gsi', 'leica_gsi');
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
insert into public.workspace_members (workspace_id, user_id, role)
values ('cccccccc-0000-0000-0000-000000000001', '22222222-2222-2222-2222-222222222222', 'admin');
select tests.ok(true, 'owner can add an admin to a team workspace');
commit;

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

-- ---------------------------------------------------------------- RLS enabled everywhere
select tests.ok(
  not exists (
    select 1 from pg_class c join pg_namespace n on n.oid = c.relnamespace
    where n.nspname = 'public' and c.relkind = 'r' and not c.relrowsecurity
      and c.relname <> 'spatial_ref_sys'
  ),
  'RLS enabled on every public table');

\echo 'ALL TESTS PASSED'
