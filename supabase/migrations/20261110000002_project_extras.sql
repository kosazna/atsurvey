-- Free-form per-project data used by the web app: levelling readings and benchmarks,
-- UI state. Covered by the existing projects RLS policies (row-level, all columns).
alter table public.projects
  add column if not exists extras jsonb not null default '{}'::jsonb;

-- keep it an object and bounded in size (levelling grids are small; this stops abuse)
alter table public.projects
  add constraint projects_extras_object check (jsonb_typeof(extras) = 'object'),
  add constraint projects_extras_size check (pg_column_size(extras) <= 1048576);

comment on column public.projects.extras is
  'Web-app data: {"leveling": {benchmarks, rows, tolerance_*, distribute}, "ui": {...}}';
