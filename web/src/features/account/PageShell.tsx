import { Link } from "@tanstack/react-router";
import { ArrowLeft } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Logo } from "@/components/Logo";
import { UserMenu } from "@/components/UserMenu";
import { Button } from "@/components/ui/button";

/** Shared chrome for account-level pages (account, billing). */
export function PageShell({ title, description, children }: { title: string; description?: string; children: React.ReactNode }) {
  const { t } = useTranslation();
  return (
    <div className="flex h-full flex-col">
      <header className="flex h-(--topbar-height) shrink-0 items-center gap-3 border-b bg-surface px-4">
        <Link to="/projects" aria-label={t("projects.title")}>
          <Logo />
        </Link>
        <Button variant="ghost" size="sm" asChild className="ml-2">
          <Link to="/projects">
            <ArrowLeft /> {t("projects.title")}
          </Link>
        </Button>
        <div className="ml-auto">
          <UserMenu />
        </div>
      </header>
      <main className="flex-1 overflow-y-auto">
        <div className="mx-auto max-w-3xl space-y-6 px-4 py-8">
          <div>
            <h1 className="text-xl font-semibold tracking-tight">{title}</h1>
            {description && <p className="mt-1 text-sm text-muted">{description}</p>}
          </div>
          {children}
        </div>
      </main>
    </div>
  );
}
