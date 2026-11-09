import { cn } from "@/lib/utils";

export function SectionHeader({
  title,
  description,
  actions,
  className,
}: {
  title: React.ReactNode;
  description?: React.ReactNode;
  actions?: React.ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("flex flex-wrap items-center gap-x-4 gap-y-2 border-b px-4 py-3", className)}>
      <div className="min-w-0">
        <h2 className="text-sm font-semibold tracking-tight">{title}</h2>
        {description && <p className="mt-0.5 text-xs text-muted-foreground">{description}</p>}
      </div>
      {actions && <div className="ml-auto flex flex-wrap items-center gap-1.5">{actions}</div>}
    </div>
  );
}

export function SectionFrame({ children, className }: { children: React.ReactNode; className?: string }) {
  return <div className={cn("flex h-full min-h-[480px] flex-col lg:min-h-0", className)}>{children}</div>;
}
