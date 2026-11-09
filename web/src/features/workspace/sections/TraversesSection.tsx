import { ArrowRight, Lightbulb, Loader2, MoreHorizontal, Pencil, Plus, Route as RouteIcon, Trash2, X } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog, DialogBody, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { EmptyState } from "@/components/ui/empty";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import type { StoredTraverse } from "@/data/store";
import { api } from "@/lib/api";
import type { TraverseKind, TraverseSpec } from "@/lib/types";
import { cn, uid } from "@/lib/utils";
import { useWorkspace } from "../useWorkspace";
import { TraverseStatusBadge } from "./ReportsSection";
import { SectionFrame, SectionHeader } from "./SectionLayout";

export function RouteChips({ route, known, className }: { route: string[]; known?: Set<string>; className?: string }) {
  return (
    <div className={cn("flex flex-wrap items-center gap-1", className)}>
      {route.map((p, i) => (
        <span key={`${p}-${i}`} className="flex items-center gap-1">
          {i > 0 && <ArrowRight className="size-3 text-muted-foreground/60" />}
          <span
            className={cn(
              "rounded-md border px-1.5 py-0.5 text-xs font-medium tabular",
              known?.has(p) ? "border-pt-control/30 bg-pt-control/10 text-pt-control" : "bg-card",
            )}
          >
            {p}
          </span>
        </span>
      ))}
    </div>
  );
}

function RouteEditor({ value, onChange, options }: { value: string[]; onChange: (v: string[]) => void; options: string[] }) {
  const { t } = useTranslation();
  const [text, setText] = useState("");
  const add = (raw: string) => {
    const parts = raw
      .split(/[\s,;→>\-]+/)
      .map((s) => s.trim())
      .filter(Boolean);
    if (parts.length) onChange([...value, ...parts]);
    setText("");
  };
  return (
    <div className="space-y-2">
      <div className="flex min-h-9 flex-wrap items-center gap-1 rounded-md border border-input bg-card p-1.5 shadow-xs focus-within:border-ring focus-within:ring-3 focus-within:ring-ring/25">
        {value.map((p, i) => (
          <span key={`${p}-${i}`} className="flex items-center gap-1">
            {i > 0 && <ArrowRight className="size-3 text-muted-foreground/60" />}
            <span className="flex items-center gap-0.5 rounded-md bg-muted py-0.5 pl-1.5 pr-0.5 text-xs font-medium">
              {p}
              <button type="button" className="rounded p-0.5 text-muted-foreground hover:bg-background hover:text-foreground" onClick={() => onChange(value.filter((_, j) => j !== i))} aria-label={t("common.remove")}>
                <X className="size-3" />
              </button>
            </span>
          </span>
        ))}
        <input
          list="route-points"
          className="min-w-24 flex-1 bg-transparent px-1 text-sm outline-none"
          value={text}
          placeholder={value.length ? "" : t("trav.addPoint")}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" || e.key === "," || e.key === " ") {
              e.preventDefault();
              add(text);
            } else if (e.key === "Backspace" && !text && value.length) {
              onChange(value.slice(0, -1));
            }
          }}
          onBlur={() => text && add(text)}
          onPaste={(e) => {
            const s = e.clipboardData.getData("text");
            if (/[\s,;]/.test(s)) {
              e.preventDefault();
              add(s);
            }
          }}
          aria-label={t("trav.route")}
        />
        <datalist id="route-points">
          {options.map((o) => (
            <option key={o} value={o} />
          ))}
        </datalist>
      </div>
      <p className="text-xs text-muted-foreground">{t("trav.routeHint")}</p>
    </div>
  );
}

function TraverseDialog({ initial, onSave, onClose, options }: { initial: StoredTraverse; onSave: (t: StoredTraverse) => void; onClose: () => void; options: string[] }) {
  const { t } = useTranslation();
  const [v, setV] = useState<StoredTraverse>(initial);
  const eo = v.end_orientation === null || v.end_orientation === undefined ? "auto" : v.end_orientation ? "yes" : "no";
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{initial.route.length ? t("trav.edit") : t("trav.add")}</DialogTitle>
          <DialogDescription>{t("trav.emptyHint")}</DialogDescription>
        </DialogHeader>
        <DialogBody className="space-y-4">
          <div className="space-y-1.5">
            <Label htmlFor="tr-name">{t("trav.name")}</Label>
            <Input id="tr-name" value={v.name ?? ""} onChange={(e) => setV({ ...v, name: e.target.value })} placeholder={v.route.length ? v.route.join("-") : ""} />
          </div>
          <div className="space-y-1.5">
            <Label>{t("trav.route")}</Label>
            <RouteEditor value={v.route} onChange={(route) => setV({ ...v, route })} options={options} />
          </div>
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="space-y-1.5">
              <Label>{t("trav.kind")}</Label>
              <Select<TraverseKind>
                value={v.kind ?? "auto"}
                onValueChange={(kind) => setV({ ...v, kind })}
                options={(["auto", "link", "closed", "open"] as TraverseKind[]).map((k) => ({ value: k, label: t(`traverseKind.${k}`) }))}
              />
            </div>
            <div className="space-y-1.5">
              <Label>{t("trav.endOrientation")}</Label>
              <Select<"auto" | "yes" | "no">
                value={eo}
                onValueChange={(x) => setV({ ...v, end_orientation: x === "auto" ? null : x === "yes" })}
                options={[
                  { value: "auto", label: t("trav.endOrientationAuto") },
                  { value: "yes", label: t("common.yes") },
                  { value: "no", label: t("common.no") },
                ]}
              />
            </div>
          </div>
        </DialogBody>
        <DialogFooter>
          {v.route.length > 0 && v.route.length < 3 && <span className="mr-auto text-xs text-destructive">{t("trav.tooShort")}</span>}
          <Button variant="ghost" onClick={onClose}>
            {t("common.cancel")}
          </Button>
          <Button onClick={() => onSave(v)} disabled={v.route.length < 3}>
            {t("common.save")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export function TraversesSection() {
  const { t } = useTranslation();
  const ws = useWorkspace();
  const travs = ws.data.traverses;
  const [editing, setEditing] = useState<StoredTraverse | null>(null);
  const [suggestions, setSuggestions] = useState<TraverseSpec[] | null>(null);
  const [loadingSug, setLoadingSug] = useState(false);
  const known = new Set(ws.data.control_points.map((p) => p.name));
  const options = [...new Set([...ws.data.control_points.map((p) => p.name), ...ws.data.setups.map((s) => s.station), ...ws.data.setups.flatMap((s) => s.observations.map((o) => o.target))])].filter(Boolean).sort();

  const results = new Map((ws.result?.traverses ?? []).map((r) => [r.id ?? r.name, r]));

  const save = (tr: StoredTraverse) => {
    const exists = travs.some((x) => x.id === tr.id);
    ws.update({ traverses: exists ? travs.map((x) => (x.id === tr.id ? tr : x)) : [...travs, tr] });
    setEditing(null);
  };

  const suggest = async () => {
    setLoadingSug(true);
    try {
      const s = await api.suggestTraverses(ws.input);
      const existing = new Set(travs.map((x) => x.route.join(">")));
      const fresh = s.filter((x) => !existing.has(x.route.join(">")) && !existing.has([...x.route].reverse().join(">")));
      if (!fresh.length) toast.info(t("trav.noSuggestions"));
      setSuggestions(fresh.length ? fresh : null);
    } catch (e) {
      toast.error(t("errors.api", { message: (e as Error).message }));
    } finally {
      setLoadingSug(false);
    }
  };

  const accept = (list: TraverseSpec[]) => {
    ws.update({
      traverses: [
        ...travs,
        ...list.map((s) => ({ id: uid(), name: s.name ?? null, route: s.route, kind: s.kind ?? "auto", end_orientation: s.end_orientation ?? null, enabled: true })),
      ],
    });
    setSuggestions((prev) => {
      const left = (prev ?? []).filter((p) => !list.includes(p));
      return left.length ? left : null;
    });
  };

  const newTraverse = (): StoredTraverse => ({ id: uid(), name: "", route: [], kind: "auto", end_orientation: null, enabled: true });

  return (
    <SectionFrame>
      <SectionHeader
        title={t("trav.title")}
        actions={
          <>
            <Button variant="outline" size="sm" onClick={suggest} disabled={loadingSug} data-testid="btn-suggest">
              {loadingSug ? <Loader2 className="animate-spin" /> : <Lightbulb />} {loadingSug ? t("trav.suggesting") : t("trav.suggest")}
            </Button>
            <Button size="sm" onClick={() => setEditing(newTraverse())}>
              <Plus /> {t("trav.add")}
            </Button>
          </>
        }
      />
      <div className="min-h-0 flex-1 overflow-y-auto p-4">
        {suggestions && (
          <div className="mb-4 rounded-xl border border-primary/30 bg-primary/5 p-3">
            <div className="mb-2 flex items-center gap-2">
              <Lightbulb className="size-4 text-primary" />
              <div className="text-sm font-medium">{t("trav.suggestionsTitle")}</div>
              <span className="text-xs text-muted-foreground">{t("trav.suggestionsHint")}</span>
              <Button size="sm" variant="ghost" className="ml-auto" onClick={() => accept(suggestions)}>
                {t("trav.acceptAll")}
              </Button>
              <Button size="icon-sm" variant="ghost" onClick={() => setSuggestions(null)} aria-label={t("common.close")}>
                <X />
              </Button>
            </div>
            <div className="space-y-1.5">
              {suggestions.map((s, i) => (
                <div key={i} className="flex items-center gap-2 rounded-lg border bg-card px-3 py-2">
                  <RouteChips route={s.route} known={known} className="flex-1" />
                  {s.kind && s.kind !== "auto" && <Badge variant="secondary">{t(`traverseKind.${s.kind}`)}</Badge>}
                  <Button size="sm" variant="outline" onClick={() => accept([s])}>
                    <Plus /> {t("trav.accept")}
                  </Button>
                </div>
              ))}
            </div>
          </div>
        )}

        {travs.length === 0 ? (
          <EmptyState
            icon={<RouteIcon />}
            title={t("trav.empty")}
            description={t("trav.emptyHint")}
            action={
              <div className="flex gap-2">
                <Button size="sm" variant="outline" onClick={suggest}>
                  <Lightbulb /> {t("trav.suggest")}
                </Button>
                <Button size="sm" onClick={() => setEditing(newTraverse())}>
                  <Plus /> {t("trav.add")}
                </Button>
              </div>
            }
          />
        ) : (
          <div className="space-y-2">
            {travs.map((tr) => {
              const res = results.get(tr.id) ?? results.get(tr.name ?? "");
              return (
                <div key={tr.id} className={cn("flex flex-wrap items-center gap-3 rounded-xl border bg-card px-3.5 py-3 shadow-xs", !tr.enabled && "opacity-60")}>
                  <Switch checked={tr.enabled ?? true} onCheckedChange={(enabled) => save({ ...tr, enabled })} aria-label={t("trav.enabled")} />
                  <div className="min-w-0 flex-1">
                    <div className="mb-1.5 flex items-center gap-2">
                      <span className="truncate text-sm font-medium">{tr.name || tr.route.join("-")}</span>
                      <Badge variant="secondary">{t(`traverseKind.${res?.kind ?? tr.kind ?? "auto"}`)}</Badge>
                    </div>
                    <RouteChips route={tr.route} known={known} />
                  </div>
                  {res ? <TraverseStatusBadge status={res.status} /> : tr.enabled && <Badge variant="secondary">{t("trav.status.pending")}</Badge>}
                  <DropdownMenu>
                    <DropdownMenuTrigger asChild>
                      <Button variant="ghost" size="icon-sm" aria-label="Menu">
                        <MoreHorizontal />
                      </Button>
                    </DropdownMenuTrigger>
                    <DropdownMenuContent align="end">
                      <DropdownMenuItem onSelect={() => setEditing(tr)}>
                        <Pencil /> {t("trav.edit")}
                      </DropdownMenuItem>
                      {res && (
                        <DropdownMenuItem onSelect={() => ws.goTo("reports", { traverse: tr.id })}>
                          <RouteIcon /> {t("reports.showSheet")}
                        </DropdownMenuItem>
                      )}
                      <DropdownMenuSeparator />
                      <DropdownMenuItem destructive onSelect={() => ws.update({ traverses: travs.filter((x) => x.id !== tr.id) })}>
                        <Trash2 /> {t("common.delete")}
                      </DropdownMenuItem>
                    </DropdownMenuContent>
                  </DropdownMenu>
                </div>
              );
            })}
          </div>
        )}
      </div>
      {editing && <TraverseDialog initial={editing} onSave={save} onClose={() => setEditing(null)} options={options} />}
    </SectionFrame>
  );
}
