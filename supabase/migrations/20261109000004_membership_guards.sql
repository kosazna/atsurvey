-- Membership and plan-limit guards (review follow-up to the init migration).
--
-- 1. Only owners may grant or revoke the 'owner' role (admins could otherwise promote
--    themselves).
-- 2. Personal-workspace memberships cannot be removed (the workspace would be orphaned),
--    and a workspace must always keep at least one owner.
-- 3. The free-plan project limit also applies when a project is moved into another
--    workspace (update of workspace_id).

create or replace function public.guard_workspace_members()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
declare
  is_owner boolean;
  remaining_owners integer;
begin
  -- the service role (and migrations/triggers running without a JWT) are trusted
  if (select auth.uid()) is null then
    return coalesce(new, old);
  end if;

  is_owner := public.has_workspace_role(
    coalesce(new.workspace_id, old.workspace_id), array['owner']::public.workspace_role[]
  );

  -- bootstrap: the creator becomes the first owner of a workspace that has no members yet
  if tg_op = 'INSERT' and new.role = 'owner'
     and not exists (select 1 from public.workspace_members m where m.workspace_id = new.workspace_id)
     and exists (
       select 1 from public.workspaces w
       where w.id = new.workspace_id and w.created_by = new.user_id
     ) then
    return new;
  end if;

  if tg_op in ('INSERT', 'UPDATE') and new.role = 'owner'
     and (tg_op = 'INSERT' or old.role <> 'owner') and not is_owner then
    raise exception using errcode = '42501', message = 'only_owner_can_grant_owner';
  end if;

  if tg_op = 'UPDATE' and old.role = 'owner' and new.role <> 'owner' and not is_owner then
    raise exception using errcode = '42501', message = 'only_owner_can_revoke_owner';
  end if;

  if tg_op = 'DELETE' then
    if exists (select 1 from public.workspaces w where w.id = old.workspace_id and w.personal) then
      raise exception using errcode = '42501', message = 'personal_workspace_membership';
    end if;
  end if;

  if (tg_op = 'DELETE' and old.role = 'owner')
     or (tg_op = 'UPDATE' and old.role = 'owner' and new.role <> 'owner') then
    select count(*) into remaining_owners
    from public.workspace_members m
    where m.workspace_id = old.workspace_id and m.role = 'owner' and m.user_id <> old.user_id;
    if remaining_owners = 0 then
      raise exception using errcode = '42501', message = 'workspace_needs_an_owner';
    end if;
  end if;

  return coalesce(new, old);
end;
$$;

create trigger workspace_members_guard
  before insert or update or delete on public.workspace_members
  for each row execute function public.guard_workspace_members();

drop trigger if exists projects_enforce_limit on public.projects;
create trigger projects_enforce_limit
  before insert or update of archived_at, workspace_id on public.projects
  for each row execute function public.enforce_project_limit();

revoke execute on function public.guard_workspace_members() from public, anon, authenticated;
