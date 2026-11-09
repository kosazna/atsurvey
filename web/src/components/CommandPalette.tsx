import { Command as Cmdk } from "cmdk";
import { FolderOpen, Languages, Moon } from "lucide-react";
import { useEffect } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "@tanstack/react-router";
import { Dialog as D } from "radix-ui";
import { toggleLanguage } from "@/lib/i18n";
import { toggleTheme } from "@/lib/theme";
import { Kbd } from "./ui/kbd";
import { useCommandCtx, type Command } from "./commands";

export function CommandPalette() {
  const { t } = useTranslation();
  const { page, open, setOpen } = useCommandCtx();
  const navigate = useNavigate();

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setOpen(!open);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, setOpen]);

  const global: Command[] = [
    { id: "projects", group: t("cmd.navigation"), label: t("cmd.allProjects"), icon: <FolderOpen />, run: () => void navigate({ to: "/projects" }) },
    { id: "theme", group: t("cmd.actions"), label: t("cmd.toggleTheme"), icon: <Moon />, run: toggleTheme },
    { id: "lang", group: t("cmd.actions"), label: t("cmd.toggleLang"), icon: <Languages />, run: toggleLanguage },
  ];
  const all = [...page, ...global];
  const groups = [...new Set(all.map((c) => c.group))];

  return (
    <D.Root open={open} onOpenChange={setOpen}>
      <D.Portal>
        <D.Overlay className="fixed inset-0 z-50 bg-black/30 data-[state=open]:animate-in" />
        <D.Content className="fixed left-1/2 top-[15vh] z-50 w-[calc(100vw-2rem)] max-w-xl -translate-x-1/2 overflow-hidden rounded-xl border bg-popover shadow-2xl data-[state=open]:animate-in">
          <D.Title className="sr-only">Command palette</D.Title>
          <Cmdk label="Command palette" className="[&_[cmdk-group-heading]]:px-3 [&_[cmdk-group-heading]]:pb-1 [&_[cmdk-group-heading]]:pt-2 [&_[cmdk-group-heading]]:text-[11px] [&_[cmdk-group-heading]]:font-medium [&_[cmdk-group-heading]]:text-muted-foreground">
            <Cmdk.Input
              placeholder={t("cmd.placeholder")}
              className="h-11 w-full border-b bg-transparent px-4 text-sm outline-none placeholder:text-muted-foreground"
            />
            <Cmdk.List className="max-h-80 overflow-y-auto p-1.5">
              <Cmdk.Empty className="px-3 py-6 text-center text-sm text-muted-foreground">{t("cmd.empty")}</Cmdk.Empty>
              {groups.map((g) => (
                <Cmdk.Group key={g} heading={g}>
                  {all
                    .filter((c) => c.group === g)
                    .map((c) => (
                      <Cmdk.Item
                        key={c.id}
                        value={`${c.label} ${(c.keywords ?? []).join(" ")}`}
                        onSelect={() => {
                          setOpen(false);
                          c.run();
                        }}
                        className="flex cursor-pointer items-center gap-2.5 rounded-md px-3 py-2 text-sm data-[selected=true]:bg-accent [&_svg]:size-4 [&_svg]:text-muted-foreground"
                      >
                        {c.icon}
                        <span className="flex-1">{c.label}</span>
                        {c.shortcut && <Kbd>{c.shortcut}</Kbd>}
                      </Cmdk.Item>
                    ))}
                </Cmdk.Group>
              ))}
            </Cmdk.List>
          </Cmdk>
        </D.Content>
      </D.Portal>
    </D.Root>
  );
}
