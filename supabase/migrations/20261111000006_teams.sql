-- Team workspaces: membership by invitation and consent (security plan phase 3, DB-15).
--
-- DB-15 owners and admins could insert any user id straight into their workspace: no consent,
--       and a way to push data at someone. Membership now comes only from accepting an
--       invitation addressed to the user's confirmed e-mail (and from the owner trigger when a
--       workspace is created). No secret link exists that could leak: the invitee sees pending
--       invitations in the app after signing in with that e-mail.
-- Also: roster with names/e-mails visible to fellow members only, ownership transfer, a
-- workspace list with role and plan for the switcher.

create table public.workspace_invitations (
  id uuid primary key default gen_random_uuid(),
  workspace_id uuid not null references public.workspaces (id) on delete cascade,
  email text not null check (
    email = lower(email) and length(email) <= 254 and email ~ '^[^@\s]+@[^@\s]+\.[^@\s]+$'),
  role public.workspace_role not null check (role <> 'owner'),
  invited_by uuid references auth.users (id) on delete set null,
  created_at timestamptz not null default now(),
  expires_at timestamptz not null default now() + interval '7 days',
  accepted_at timestamptz,
  declined_at timestamptz,
  revoked_at timestamptz
);
create unique index workspace_invitations_pending_idx on public.workspace_invitations (workspace_id, email)
  where accepted_at is null and declined_at is null and revoked_at is null;
create index workspace_invitations_email_idx on public.workspace_invitations (email);
create index workspace_invitations_invited_by_idx on public.workspace_invitations (invited_by);

alter table public.workspace_invitations enable row level security;
create policy invitations_select on public.workspace_invitations for select to authenticated
  using (public.has_workspace_role(workspace_id, array['owner', 'admin']::public.workspace_role[]));
revoke all on public.workspace_invitations from anon, authenticated;
grant select on public.workspace_invitations to authenticated;

-- membership only through accept_invitation() and the owner trigger (both security definer)
drop policy members_insert on public.workspace_members;

-- ------------------------------------------------------------------ helpers

-- The caller's confirmed e-mail (lower case), or null if unconfirmed / not signed in.
create or replace function public.my_confirmed_email()
returns text
language sql
stable
security definer
set search_path = ''
as $$
  select lower(u.email) from auth.users u
  where u.id = (select auth.uid()) and u.email_confirmed_at is not null;
$$;

-- ------------------------------------------------------------------ invitations

create or replace function public.invite_member(p_workspace_id uuid, p_email text, p_role public.workspace_role)
returns uuid
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_email text := lower(trim(coalesce(p_email, '')));
  v_id uuid;
begin
  if not public.has_workspace_role(p_workspace_id, array['owner', 'admin']::public.workspace_role[]) then
    raise exception using errcode = '42501', message = 'not_allowed';
  end if;
  if exists (select 1 from public.workspaces w where w.id = p_workspace_id and w.personal) then
    raise exception using errcode = 'P0001', message = 'personal_workspace';
  end if;
  if p_role = 'owner' then
    raise exception using errcode = '22023', message = 'invalid_role', hint = 'Transfer ownership instead.';
  end if;
  if p_role = 'admin' and not public.has_workspace_role(p_workspace_id, array['owner']::public.workspace_role[]) then
    raise exception using errcode = '42501', message = 'only_owner_invites_admins';
  end if;
  if public.workspace_plan(p_workspace_id) <> 'pro' then
    raise exception using errcode = 'P0001', message = 'teams_require_pro';
  end if;
  if length(v_email) > 254 or v_email !~ '^[^@\s]+@[^@\s]+\.[^@\s]+$' then
    raise exception using errcode = '22023', message = 'invalid_email';
  end if;
  if exists (
    select 1 from public.workspace_members m join auth.users u on u.id = m.user_id
    where m.workspace_id = p_workspace_id and lower(u.email) = v_email
  ) then
    raise exception using errcode = 'P0001', message = 'already_member';
  end if;
  if (select count(*) from public.workspace_invitations i
      where i.workspace_id = p_workspace_id and i.accepted_at is null and i.declined_at is null
        and i.revoked_at is null and i.expires_at > now()) >= 50 then
    raise exception using errcode = 'P0001', message = 'too_many_invitations';
  end if;

  -- a new invitation replaces a pending one for the same address
  update public.workspace_invitations i set revoked_at = now()
  where i.workspace_id = p_workspace_id and i.email = v_email
    and i.accepted_at is null and i.declined_at is null and i.revoked_at is null;

  insert into public.workspace_invitations (workspace_id, email, role, invited_by)
  values (p_workspace_id, v_email, p_role, (select auth.uid()))
  returning id into v_id;
  perform public.audit(p_workspace_id, null, 'member.invited', jsonb_build_object('email', v_email, 'role', p_role));
  return v_id;
end;
$$;

-- Pending invitations addressed to the caller's confirmed e-mail.
create or replace function public.my_invitations()
returns table (id uuid, workspace_id uuid, workspace_name text, role public.workspace_role,
               invited_by_name text, expires_at timestamptz)
language sql
stable
security definer
set search_path = ''
as $$
  select i.id, i.workspace_id, w.name, i.role, p.full_name, i.expires_at
  from public.workspace_invitations i
  join public.workspaces w on w.id = i.workspace_id
  left join public.profiles p on p.id = i.invited_by
  where i.email = public.my_confirmed_email()
    and i.accepted_at is null and i.declined_at is null and i.revoked_at is null
    and i.expires_at > now()
  order by i.created_at;
$$;

-- An invitation the caller may answer, or an error that reveals nothing about others.
create or replace function public.pending_invitation_for_me(p_id uuid)
returns public.workspace_invitations
language plpgsql
stable
security definer
set search_path = ''
as $$
declare
  inv public.workspace_invitations;
begin
  select * into inv from public.workspace_invitations i
  where i.id = p_id and i.email = public.my_confirmed_email()
    and i.accepted_at is null and i.declined_at is null and i.revoked_at is null
    and i.expires_at > now();
  if not found then
    raise exception using errcode = 'P0001', message = 'invitation_not_found';
  end if;
  return inv;
end;
$$;

create or replace function public.accept_invitation(p_id uuid)
returns uuid
language plpgsql
security definer
set search_path = ''
as $$
declare
  inv public.workspace_invitations := public.pending_invitation_for_me(p_id);
begin
  insert into public.workspace_members (workspace_id, user_id, role)
  values (inv.workspace_id, (select auth.uid()), inv.role)
  on conflict (workspace_id, user_id) do nothing;
  update public.workspace_invitations set accepted_at = now() where id = inv.id;
  return inv.workspace_id;
end;
$$;

create or replace function public.decline_invitation(p_id uuid)
returns void
language plpgsql
security definer
set search_path = ''
as $$
declare
  inv public.workspace_invitations := public.pending_invitation_for_me(p_id);
begin
  update public.workspace_invitations set declined_at = now() where id = inv.id;
  perform public.audit(inv.workspace_id, null, 'member.invite_declined', jsonb_build_object('email', inv.email));
end;
$$;

create or replace function public.revoke_invitation(p_id uuid)
returns void
language plpgsql
security definer
set search_path = ''
as $$
declare
  inv public.workspace_invitations;
begin
  select * into inv from public.workspace_invitations i where i.id = p_id;
  if not found or not public.has_workspace_role(inv.workspace_id, array['owner', 'admin']::public.workspace_role[]) then
    raise exception using errcode = '42501', message = 'not_allowed';
  end if;
  update public.workspace_invitations set revoked_at = now()
  where id = p_id and accepted_at is null and declined_at is null and revoked_at is null;
  perform public.audit(inv.workspace_id, null, 'member.invite_revoked', jsonb_build_object('email', inv.email));
end;
$$;

-- ------------------------------------------------------------------ roster, switcher, ownership

-- Fellow members with names and e-mails: visible to members of that workspace only.
create or replace function public.workspace_roster(p_workspace_id uuid)
returns table (user_id uuid, full_name text, email text, role public.workspace_role,
               has_mfa boolean, joined_at timestamptz)
language plpgsql
stable
security definer
set search_path = ''
as $$
begin
  if not public.is_workspace_member(p_workspace_id) then
    raise exception using errcode = '42501', message = 'not_a_member';
  end if;
  return query
    select m.user_id, p.full_name, u.email::text, m.role, public.user_has_mfa(m.user_id), m.created_at
    from public.workspace_members m
    join auth.users u on u.id = m.user_id
    left join public.profiles p on p.id = m.user_id
    where m.workspace_id = p_workspace_id
    order by case m.role when 'owner' then 0 when 'admin' then 1 when 'member' then 2 else 3 end, u.email;
end;
$$;

-- Workspaces of the caller with their role and plan (workspace switcher).
create or replace function public.my_workspaces()
returns table (id uuid, name text, personal boolean, role public.workspace_role, plan text,
               require_mfa boolean)
language sql
stable
security invoker
set search_path = ''
as $$
  select w.id, w.name, w.personal, m.role, public.workspace_plan(w.id), w.require_mfa
  from public.workspaces w
  join public.workspace_members m on m.workspace_id = w.id and m.user_id = (select auth.uid())
  order by w.personal desc, w.name;
$$;

-- The owner hands the workspace to another member and becomes an admin, atomically.
create or replace function public.transfer_ownership(p_workspace_id uuid, p_new_owner uuid)
returns void
language plpgsql
security definer
set search_path = ''
as $$
declare
  uid uuid := (select auth.uid());
begin
  if not public.has_workspace_role(p_workspace_id, array['owner']::public.workspace_role[]) then
    raise exception using errcode = '42501', message = 'not_allowed';
  end if;
  if exists (select 1 from public.workspaces w where w.id = p_workspace_id and w.personal) then
    raise exception using errcode = 'P0001', message = 'personal_workspace';
  end if;
  if p_new_owner = uid or not exists (
    select 1 from public.workspace_members m where m.workspace_id = p_workspace_id and m.user_id = p_new_owner
  ) then
    raise exception using errcode = 'P0001', message = 'not_a_member';
  end if;
  update public.workspace_members set role = 'owner'
  where workspace_id = p_workspace_id and user_id = p_new_owner;
  update public.workspace_members set role = 'admin'
  where workspace_id = p_workspace_id and user_id = uid;
end;
$$;

-- ------------------------------------------------------------------ privileges

revoke execute on function public.my_confirmed_email() from public, anon, authenticated;
revoke execute on function public.pending_invitation_for_me(uuid) from public, anon, authenticated;
revoke execute on function public.invite_member(uuid, text, public.workspace_role) from public, anon;
revoke execute on function public.my_invitations() from public, anon;
revoke execute on function public.accept_invitation(uuid) from public, anon;
revoke execute on function public.decline_invitation(uuid) from public, anon;
revoke execute on function public.revoke_invitation(uuid) from public, anon;
revoke execute on function public.workspace_roster(uuid) from public, anon;
revoke execute on function public.my_workspaces() from public, anon;
revoke execute on function public.transfer_ownership(uuid, uuid) from public, anon;
grant execute on function
  public.invite_member(uuid, text, public.workspace_role),
  public.my_invitations(),
  public.accept_invitation(uuid),
  public.decline_invitation(uuid),
  public.revoke_invitation(uuid),
  public.workspace_roster(uuid),
  public.my_workspaces(),
  public.transfer_ownership(uuid, uuid)
to authenticated;
