-- Read-only workspace members (clients, reviewers). Own migration: a new enum value cannot be
-- used in the transaction that adds it. See docs/security.md (DB-7).
alter type public.workspace_role add value if not exists 'viewer';
