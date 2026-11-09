-- Private bucket for raw instrument files.
-- Object path convention: {workspace_id}/{project_id}/{uuid}-{filename}

insert into storage.buckets (id, name, public, file_size_limit)
values ('raw-files', 'raw-files', false, 20971520)
on conflict (id) do update
  set public = excluded.public,
      file_size_limit = excluded.file_size_limit;

create policy raw_files_objects_select on storage.objects for select to authenticated
  using (
    bucket_id = 'raw-files'
    and public.is_workspace_member(public.storage_path_workspace(name))
  );

create policy raw_files_objects_insert on storage.objects for insert to authenticated
  with check (
    bucket_id = 'raw-files'
    and public.is_workspace_member(public.storage_path_workspace(name))
  );

create policy raw_files_objects_update on storage.objects for update to authenticated
  using (
    bucket_id = 'raw-files'
    and public.is_workspace_member(public.storage_path_workspace(name))
  )
  with check (
    bucket_id = 'raw-files'
    and public.is_workspace_member(public.storage_path_workspace(name))
  );

create policy raw_files_objects_delete on storage.objects for delete to authenticated
  using (
    bucket_id = 'raw-files'
    and public.is_workspace_member(public.storage_path_workspace(name))
  );
