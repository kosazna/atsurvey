import { useTranslation } from "react-i18next";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { activeTool, type ModuleId } from "../../sections";
import { useWorkspace } from "../../useWorkspace";
import { SectionFrame, SectionHeader } from "../SectionLayout";
import type { ToolEntry } from "../tools/registry";

interface ModuleSectionProps {
  id: ModuleId;
  /** the page's tabs, already in MODULE_TOOLS order */
  tools: ToolEntry[];
}

/** A page made of tool tabs (Ιδιοκτησίες, Ανάγλυφο, …); the open tab lives in the URL (?tool=). */
export function ModuleSection({ id, tools }: ModuleSectionProps) {
  const { t } = useTranslation();
  const ws = useWorkspace();
  const current = activeTool(id, ws.tool);
  const tool = tools.find((x) => x.id === current) ?? tools[0];

  return (
    <SectionFrame>
      <Tabs value={tool.id} onValueChange={ws.setTool} className="flex min-h-0 flex-1 flex-col">
        <SectionHeader title={t(`ws.sections.${id}`)} description={ws.pick ? t("tools.pickingHint") : t(`ws.sectionHints.${id}`)} />
        {tools.length > 1 && (
          <div className="overflow-x-auto border-b px-4 py-2">
            <TabsList aria-label={t(`ws.sections.${id}`)}>
              {tools.map((x) => (
                <TabsTrigger key={x.id} value={x.id} data-testid={`tool-${x.id}`}>
                  {t(`tools.tabs.${x.id}`)}
                </TabsTrigger>
              ))}
            </TabsList>
          </div>
        )}
        <div className="min-h-0 flex-1 overflow-y-auto">
          <TabsContent key={tool.id} value={tool.id} className="p-4">
            <p className="mb-4 max-w-2xl text-xs text-muted">{t(`tools.desc.${tool.id}`)}</p>
            {tool.el}
          </TabsContent>
        </div>
      </Tabs>
    </SectionFrame>
  );
}
