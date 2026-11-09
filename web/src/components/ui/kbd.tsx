import { cn } from "@/lib/utils";
export function Kbd({ children, className }: { children: React.ReactNode; className?: string }) {
  return <kbd className={cn("inline-flex h-5 min-w-5 items-center justify-center rounded border bg-surface-sunken px-1 font-sans text-xs font-medium text-muted", className)}>{children}</kbd>;
}
