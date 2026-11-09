-- Best plan across all workspaces the caller belongs to. Used by the engine API to gate
-- exports when no workspace is specified. Security invoker: RLS on subscriptions /
-- workspace_members limits it to the caller's own memberships.
create or replace function public.my_plan()
returns text
language sql
stable
security invoker
set search_path = ''
as $$
  select case when exists (
    select 1
    from public.workspace_members m
    where m.user_id = (select auth.uid())
      and public.workspace_plan(m.workspace_id) = 'pro'
  ) then 'pro' else 'free' end;
$$;

revoke execute on function public.my_plan() from public, anon;
grant execute on function public.my_plan() to authenticated, service_role;
