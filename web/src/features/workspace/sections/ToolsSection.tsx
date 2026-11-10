import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { cn } from "@/lib/utils";
import { useWorkspace } from "../useWorkspace";
import { SectionFrame, SectionHeader } from "./SectionLayout";
import { AreaTool, ResectionTool, StakeoutTool, TransformTool } from "./tools/advanced";
import { ANALYSIS_TOOLS } from "./tools/analysis";
import { IntersectionTool, InverseTool, OffsetTool, PolarTool } from "./tools/basic";
import { COORDS_TOOLS } from "./tools/coords";
import { INSTRUMENTS_TOOLS } from "./tools/instruments";
import { PARCELS_TOOLS } from "./tools/parcels";
import type { ToolGroup } from "./tools/registry";
import { SETOUT_TOOLS } from "./tools/setout";
import { SURFACES_TOOLS } from "./tools/surfaces";

const GROUPS: ToolGroup[] = [
  {
    id: "basic",
    tools: [
      { id: "inverse", el: <InverseTool /> },
      { id: "polar", el: <PolarTool /> },
      { id: "intersection", el: <IntersectionTool /> },
      { id: "resection", el: <ResectionTool /> },
      { id: "area", el: <AreaTool /> },
      { id: "transform", el: <TransformTool /> },
      { id: "offset", el: <OffsetTool /> },
      { id: "stakeout", el: <StakeoutTool /> },
    ],
  },
  { id: "parcels", tools: PARCELS_TOOLS },
  { id: "surfaces", tools: SURFACES_TOOLS },
  { id: "setout", tools: SETOUT_TOOLS },
  { id: "coords", tools: COORDS_TOOLS },
  { id: "analysis", tools: ANALYSIS_TOOLS },
  { id: "instruments", tools: INSTRUMENTS_TOOLS },
].filter((g) => g.tools.length > 0);

export default function ToolsSection() {
  const { t } = useTranslation();
  const ws = useWorkspace();
  const [groupId, setGroupId] = useState(GROUPS[0].id);
  const group = GROUPS.find((g) => g.id === groupId) ?? GROUPS[0];
  const [tab, setTab] = useState(group.tools[0].id);

  function selectGroup(id: string) {
    const next = GROUPS.find((g) => g.id === id);
    if (!next) return;
    setGroupId(id);
    setTab(next.tools[0].id);
    ws.setPick(null);
  }

  return (
    <SectionFrame>
      <Tabs
        value={tab}
        className="flex min-h-0 flex-1 flex-col"
        onValueChange={(v) => {
          setTab(v);
          ws.setPick(null);
        }}
      >
        <SectionHeader title={t("tools.title")} description={ws.pick ? t("tools.pickingHint") : t("tools.subtitle")} />
        {GROUPS.length > 1 && (
          <div className="flex flex-wrap gap-1 border-b px-4 pt-2 pb-1" role="group" aria-label={t("tools.title")}>
            {GROUPS.map((g) => (
              <button
                key={g.id}
                type="button"
                aria-pressed={g.id === group.id}
                data-testid={`tool-group-${g.id}`}
                onClick={() => selectGroup(g.id)}
                className={cn(
                  "rounded-md px-2.5 py-1 text-xs font-medium",
                  g.id === group.id ? "bg-accent-subtle text-fg" : "text-muted hover:bg-accent-subtle",
                )}
              >
                {t(`tools.groups.${g.id}`)}
              </button>
            ))}
          </div>
        )}
        <div className="overflow-x-auto border-b px-4 py-2">
          <TabsList>
            {group.tools.map((tool) => (
              <TabsTrigger key={tool.id} value={tool.id} data-testid={`tool-${tool.id}`}>
                {t(`tools.tabs.${tool.id}`)}
              </TabsTrigger>
            ))}
          </TabsList>
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto">
          {group.tools.map((tool) => (
            <TabsContent key={tool.id} value={tool.id} className="p-4 data-[state=inactive]:hidden">
              <p className="mb-4 max-w-2xl text-xs text-muted">{t(`tools.desc.${tool.id}`)}</p>
              {tool.el}
            </TabsContent>
          ))}
        </div>
      </Tabs>
    </SectionFrame>
  );
}
