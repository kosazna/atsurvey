import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Dialog, DialogBody, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "./ui/dialog";
import { Kbd } from "./ui/kbd";

const SHORTCUTS: { keys: string[]; label: string }[] = [
  { keys: ["⌘", "K"], label: "palette" },
  { keys: ["⌘", "↵"], label: "compute" },
  { keys: ["⌘", "I"], label: "import" },
  { keys: ["⌘", "E"], label: "export" },
  { keys: ["⌘", "Z"], label: "undo" },
  { keys: ["⇧", "⌘", "Z"], label: "redo" },
  { keys: ["⌘", "⇧", "M"], label: "map" },
  { keys: ["⌘", "C"], label: "copy" },
  { keys: ["⌘", "V"], label: "paste" },
  { keys: ["Esc"], label: "cancel" },
  { keys: ["?"], label: "help" },
];

function isTyping(t: EventTarget | null) {
  const el = t as HTMLElement | null;
  return !!el && (el.tagName === "INPUT" || el.tagName === "TEXTAREA" || el.isContentEditable);
}

/** Keyboard shortcut reference. Opens on "?" or the `ats:shortcuts` window event. */
export function ShortcutsDialog() {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "?" && !e.metaKey && !e.ctrlKey && !isTyping(e.target)) {
        e.preventDefault();
        setOpen(true);
      }
    };
    const onEvent = () => setOpen(true);
    window.addEventListener("keydown", onKey);
    window.addEventListener("ats:shortcuts", onEvent);
    return () => {
      window.removeEventListener("keydown", onKey);
      window.removeEventListener("ats:shortcuts", onEvent);
    };
  }, []);
  const isMac = typeof navigator !== "undefined" && /Mac|iPhone|iPad/.test(navigator.platform);
  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t("shortcuts.title")}</DialogTitle>
          <DialogDescription>{isMac ? t("shortcuts.mac") : t("shortcuts.other")}</DialogDescription>
        </DialogHeader>
        <DialogBody>
          <dl className="divide-y" data-testid="shortcuts">
            {SHORTCUTS.map((s) => (
              <div key={s.label} className="flex items-center justify-between gap-4 py-2 text-sm">
                <dt>{t(`shortcuts.items.${s.label}`)}</dt>
                <dd className="flex gap-1">
                  {s.keys.map((k) => (
                    <Kbd key={k}>{!isMac && k === "⌘" ? "Ctrl" : k}</Kbd>
                  ))}
                </dd>
              </div>
            ))}
          </dl>
        </DialogBody>
      </DialogContent>
    </Dialog>
  );
}
