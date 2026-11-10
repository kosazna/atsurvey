import { useQuery } from "@tanstack/react-query";
import { Download, FileText } from "lucide-react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { useSession } from "@/data/session";
import { type RawFileInfo, lifecycle } from "@/data/lifecycle";
import { supabase } from "@/lib/supabase";
import { relativeTime } from "@/lib/utils";

const KB = 1024;

function size(bytes: number | null): string {
  if (bytes === null) return "";
  return bytes < KB * KB ? `${Math.max(1, Math.round(bytes / KB))} KB` : `${(bytes / KB / KB).toFixed(1)} MB`;
}

/** Instrument files stored with the project (signed-in only), downloadable through a 60 s link. */
export function RawFilesCard({ projectId }: { projectId: string }) {
  const { t, i18n } = useTranslation();
  const { mode } = useSession();
  const files = useQuery({
    queryKey: ["raw-files", projectId],
    queryFn: () => lifecycle.rawFiles(supabase!, projectId),
    enabled: mode === "cloud" && Boolean(supabase),
  });
  if (mode !== "cloud") return null;

  async function download(f: RawFileInfo) {
    try {
      const url = await lifecycle.downloadUrl(supabase!, f);
      window.location.assign(url);
    } catch (e) {
      toast.error((e as Error).message);
    }
  }

  return (
    <Card className="p-4" data-testid="raw-files-card">
      <div className="text-sm font-semibold">{t("life.files.title")}</div>
      <p className="mb-3 text-xs text-muted">{t("life.files.text")}</p>
      {(files.data ?? []).length === 0 ? (
        <p className="text-sm text-muted">{t("life.files.empty")}</p>
      ) : (
        <ul className="divide-y">
          {(files.data ?? []).map((f) => (
            <li key={f.id} className="flex items-center gap-3 py-2 text-sm">
              <FileText className="size-4 shrink-0 text-muted" />
              <div className="min-w-0 flex-1">
                <div className="truncate font-medium">{f.filename}</div>
                <div className="text-xs text-muted">
                  {f.format} · {size(f.size_bytes)} · {relativeTime(f.created_at, i18n.language)}
                </div>
              </div>
              <Button size="sm" variant="ghost" onClick={() => void download(f)}>
                <Download /> {t("life.files.download")}
              </Button>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}
