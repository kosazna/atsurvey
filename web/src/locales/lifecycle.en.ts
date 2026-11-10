import type { LifecycleMessages } from "./lifecycle.el";

const lifecycleEn: LifecycleMessages = {
  life: {
    tabs: { active: "Active", archived: "Archived", trash: "Trash" },
    archive: "Archive",
    archived: "Project archived. It no longer counts towards the project limit.",
    unarchive: "Restore",
    unarchived: "Project is active again.",
    duplicate: "Duplicate",
    duplicateName: "{{name}} (copy)",
    duplicated: "Copy created.",
    trashed: "Project moved to the trash for {{days}} days.",
    undo: "Undo",
    restore: "Restore",
    restored: "Project restored.",
    deleteForever: "Delete forever",
    deleteForeverConfirm: "Permanently delete “{{name}}” with all runs and files? This cannot be undone.",
    deletedForever: "Project permanently deleted.",
    purgeIn: "deleted in {{days}} days",
    emptyArchived: "No archived projects.",
    emptyTrash: "The trash is empty. Projects stay here for 30 days before they are deleted for good.",
    trashHint: "Deleted projects stay in the trash for 30 days and can be restored.",
    copySettings: "Settings from",
    copySettingsNone: "Defaults",
    files: {
      title: "Original files",
      text: "The instrument files as imported, with their SHA-256 fingerprint.",
      download: "Download",
      empty: "No files have been imported into this project.",
    },
    runs: {
      label: "Name",
      labelPlaceholder: "e.g. Final solution",
      saved: "Saved.",
      delete: "Delete run",
      deleted: "Run deleted.",
    },
  },
};

export default lifecycleEn;
