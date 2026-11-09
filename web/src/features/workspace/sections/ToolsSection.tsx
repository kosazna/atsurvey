import { useTranslation } from "react-i18next";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useWorkspace } from "../useWorkspace";
import { SectionFrame, SectionHeader } from "./SectionLayout";
import { AreaTool, ResectionTool, StakeoutTool, TransformTool } from "./tools/advanced";
import { IntersectionTool, InverseTool, OffsetTool, PolarTool } from "./tools/basic";

const TOOLS = [
  { id: "inverse", el: <InverseTool /> },
  { id: "polar", el: <PolarTool /> },
  { id: "intersection", el: <IntersectionTool /> },
  { id: "resection", el: <ResectionTool /> },
  { id: "area", el: <AreaTool /> },
  { id: "transform", el: <TransformTool /> },
  { id: "offset", el: <OffsetTool /> },
  { id: "stakeout", el: <StakeoutTool /> },
] as const;

export default function ToolsSection() {
  const { t } = useTranslation();
  const ws = useWorkspace();
  return (
    <SectionFrame>
      <Tabs
        defaultValue="inverse"
        className="flex min-h-0 flex-1 flex-col"
        onValueChange={() => {
          ws.setPick(null);
        }}
      >
        <SectionHeader title={t("tools.title")} description={ws.pick ? t("tools.pickingHint") : t("tools.subtitle")} />
        <div className="overflow-x-auto border-b px-4 py-2">
          <TabsList>
            {TOOLS.map((tool) => (
              <TabsTrigger key={tool.id} value={tool.id} data-testid={`tool-${tool.id}`}>
                {t(`tools.tabs.${tool.id}`)}
              </TabsTrigger>
            ))}
          </TabsList>
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto">
          {TOOLS.map((tool) => (
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
