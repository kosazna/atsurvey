-- Two-factor authentication enforced by the database (security plan phase 2, DB-14).
--
-- * A user who has a verified authenticator (TOTP) reaches their workspaces only from an aal2
--   session: a stolen password alone (aal1) sees nothing.
-- * A workspace owner can require two-factor for everyone in the workspace (require_mfa);
--   members without it are locked out of that workspace until they enable it.
-- Enforced in the four access helpers every policy uses, so every table and storage object
-- follows. Changing require_mfa needs the owner role from an aal2 session.

alter table public.workspaces add column require_mfa boolean not null default false;

-- True when the caller's session satisfies the two-factor rules for this workspace.
create or replace function public.mfa_satisfied(p_workspace_id uuid)
returns boolean
language sql
stable
security definer
set search_path = ''
as $$
  select coalesce(auth.jwt() ->> 'aal', 'aal1') = 'aal2'
    or (
      not exists (
        select 1 from auth.mfa_factors f
        where f.user_id = (select auth.uid()) and f.status = 'verified')
      and not exists (
        select 1 from public.workspaces w where w.id = p_workspace_id and w.require_mfa)
    );
$$;

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
  ) and public.mfa_satisfied(p_workspace_id);
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
  ) and public.mfa_satisfied(p_workspace_id);
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
      and public.mfa_satisfied(p.workspace_id)
  );
$$;

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
      and public.mfa_satisfied(p.workspace_id)
  );
$$;

-- The creator clause (needed to read a workspace back right after creating it) must obey the
-- two-factor rules too.
drop policy workspaces_select on public.workspaces;
create policy workspaces_select on public.workspaces for select to authenticated
  using (
    (public.is_workspace_member(id) or created_by = (select auth.uid()))
    and public.mfa_satisfied(id)
  );

-- Only an owner, from a two-factor session, may switch the requirement on or off.
create or replace function public.guard_require_mfa()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
begin
  if (select auth.uid()) is null or new.require_mfa = old.require_mfa then
    return new;
  end if;
  if coalesce(auth.jwt() ->> 'aal', 'aal1') <> 'aal2'
     or not public.has_workspace_role(new.id, array['owner']::public.workspace_role[]) then
    raise exception using
      errcode = '42501',
      message = 'require_mfa_needs_owner_aal2',
      hint = 'Only an owner signed in with two-factor authentication can change this.';
  end if;
  if new.require_mfa then
    perform public.audit(new.id, null, 'workspace.mfa_required');
  else
    perform public.audit(new.id, null, 'workspace.mfa_optional');
  end if;
  return new;
end;
$$;
create trigger workspaces_guard_require_mfa
  before update of require_mfa on public.workspaces
  for each row execute function public.guard_require_mfa();

-- The member list and invitations (phase 3) show whether someone has two-factor on.
create or replace function public.user_has_mfa(p_user uuid)
returns boolean
language sql
stable
security definer
set search_path = ''
as $$
  select exists (select 1 from auth.mfa_factors f where f.user_id = p_user and f.status = 'verified');
$$;

revoke execute on function public.mfa_satisfied(uuid) from public, anon;
revoke execute on function public.guard_require_mfa() from public, anon, authenticated;
revoke execute on function public.user_has_mfa(uuid) from public, anon, authenticated;
grant execute on function public.mfa_satisfied(uuid) to authenticated, service_role;
grant execute on function public.user_has_mfa(uuid) to service_role;
