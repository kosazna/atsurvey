import { cva, type VariantProps } from "class-variance-authority";
import * as React from "react";
import { cn } from "@/lib/utils";

const badgeVariants = cva("inline-flex items-center gap-1 rounded-md border px-1.5 py-0.5 text-[11px] font-medium leading-none whitespace-nowrap [&_svg]:size-3", {
  variants: {
    variant: {
      default: "border-transparent bg-primary/10 text-primary",
      secondary: "border-transparent bg-muted text-muted-foreground",
      outline: "text-foreground",
      success: "border-transparent bg-success/12 text-success",
      warning: "border-transparent bg-warning/15 text-[color-mix(in_oklch,var(--warning)_75%,var(--foreground))]",
      destructive: "border-transparent bg-destructive/12 text-destructive",
    },
  },
  defaultVariants: { variant: "default" },
});

export function Badge({ className, variant, ...props }: React.HTMLAttributes<HTMLSpanElement> & VariantProps<typeof badgeVariants>) {
  return <span className={cn(badgeVariants({ variant }), className)} {...props} />;
}
