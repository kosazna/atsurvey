import { Check, CreditCard, Keyboard, Languages, LogOut, Moon, Settings2, Sun, Trash2, UserRound } from "lucide-react";
import { toast } from "sonner";
import { useTranslation } from "react-i18next";
import { useNavigate } from "@tanstack/react-router";
import { useSession } from "@/data/session";
import { toggleLanguage } from "@/lib/i18n";
import { toggleTheme, useTheme } from "@/lib/theme";
import { Button } from "./ui/button";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuLabel, DropdownMenuSeparator, DropdownMenuTrigger } from "./ui/dropdown-menu";

export function UserMenu() {
  const { t, i18n } = useTranslation();
  const { mode, session, signOut, clearDemoData } = useSession();
  const theme = useTheme();
  const navigate = useNavigate();
  const email = session?.user.email;
  const initial = (email ?? "D")[0].toUpperCase();
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" size="icon" aria-label="Account" className="rounded-full">
          <span className="flex size-7 items-center justify-center rounded-full bg-accent-subtle text-xs font-semibold text-accent">
            {mode === "demo" ? <UserRound className="size-3.5" /> : initial}
          </span>
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-56">
        <DropdownMenuLabel className="truncate">{mode === "demo" ? t("common.demo") : email}</DropdownMenuLabel>
        <DropdownMenuSeparator />
        <DropdownMenuItem onSelect={() => void navigate({ to: "/account" })}>
          <Settings2 /> {t("account.title")}
        </DropdownMenuItem>
        <DropdownMenuItem onSelect={() => void navigate({ to: "/billing" })}>
          <CreditCard /> {t("billing.title")}
        </DropdownMenuItem>
        <DropdownMenuItem onSelect={() => window.dispatchEvent(new CustomEvent("ats:shortcuts"))}>
          <Keyboard /> {t("shortcuts.title")}
        </DropdownMenuItem>
        <DropdownMenuSeparator />
        <DropdownMenuItem onSelect={toggleTheme}>
          {theme === "dark" ? <Sun /> : <Moon />}
          {theme === "dark" ? t("common.light") : t("common.dark")}
        </DropdownMenuItem>
        <DropdownMenuItem onSelect={() => i18n.language !== "el" && toggleLanguage()}>
          <Languages /> Ελληνικά {i18n.language === "el" && <Check className="ml-auto" />}
        </DropdownMenuItem>
        <DropdownMenuItem onSelect={() => i18n.language !== "en" && toggleLanguage()}>
          <Languages /> English {i18n.language === "en" && <Check className="ml-auto" />}
        </DropdownMenuItem>
        <DropdownMenuSeparator />
        {mode === "demo" && (
          <DropdownMenuItem
            onSelect={() =>
              toast(t("sec.demoDataConfirm"), {
                action: {
                  label: t("sec.demoData"),
                  onClick: () => {
                    clearDemoData();
                    toast.success(t("sec.demoDataDone"));
                    window.location.assign("/projects");
                  },
                },
              })
            }
          >
            <Trash2 /> {t("sec.demoData")}
          </DropdownMenuItem>
        )}
        <DropdownMenuItem
          onSelect={async () => {
            await signOut();
            void navigate({ to: "/" });
          }}
        >
          <LogOut /> {t("common.signOut")}
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
