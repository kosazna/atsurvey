import { cn } from "@/lib/utils";

export function Logo({ className, withText = true }: { className?: string; withText?: boolean }) {
  return (
    <span className={cn("inline-flex items-center gap-2 font-semibold tracking-tight", className)}>
      <svg viewBox="0 0 32 32" className="size-6" aria-hidden>
        <rect width="32" height="32" rx="7" className="fill-foreground" />
        <path d="M16 6 26 24H6z" fill="none" stroke="#38bdf8" strokeWidth="2.4" strokeLinejoin="round" />
        <circle cx="16" cy="18" r="2.6" className="fill-background" />
      </svg>
      {withText && <span>ATSurvey</span>}
    </span>
  );
}
