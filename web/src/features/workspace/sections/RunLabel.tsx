import { Pencil } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import { Input } from "@/components/ui/input";

/** Inline-editable name of a saved run ("Τελική λύση"); read-only for viewers. */
export function RunLabel({ label, readOnly, onSave }: { label: string | null | undefined; readOnly: boolean; onSave: (label: string | null) => Promise<void> }) {
  const { t } = useTranslation();
  const [editing, setEditing] = useState(false);
  const [value, setValue] = useState(label ?? "");

  async function commit() {
    setEditing(false);
    if ((label ?? "") === value.trim()) return;
    try {
      await onSave(value.trim() || null);
      toast.success(t("life.runs.saved"));
    } catch (e) {
      toast.error((e as Error).message);
    }
  }

  if (editing) {
    return (
      <Input
        autoFocus
        maxLength={200}
        value={value}
        placeholder={t("life.runs.labelPlaceholder")}
        aria-label={t("life.runs.label")}
        className="h-7"
        onChange={(e) => setValue(e.target.value)}
        onBlur={() => void commit()}
        onKeyDown={(e) => {
          if (e.key === "Enter") void commit();
          if (e.key === "Escape") setEditing(false);
        }}
      />
    );
  }
  if (readOnly) return label ? <div className="font-medium">{label}</div> : null;
  return (
    <button type="button" className="group flex items-center gap-1 text-left font-medium" onClick={() => setEditing(true)} data-testid="run-label">
      {label || <span className="font-normal text-muted">{t("life.runs.labelPlaceholder")}</span>}
      <Pencil className="size-3 opacity-0 group-hover:opacity-60" />
    </button>
  );
}
