import { Tooltip as T } from "radix-ui";
import * as React from "react";
import { cn } from "@/lib/utils";

export const TooltipProvider = T.Provider;

export function Tooltip({ content, children, side = "bottom" }: { content: React.ReactNode; children: React.ReactNode; side?: "top" | "bottom" | "left" | "right" }) {
  return (
    <T.Root delayDuration={300}>
      <T.Trigger asChild>{children}</T.Trigger>
      <T.Portal>
        <T.Content side={side} sideOffset={6} className={cn("z-50 rounded-md bg-foreground px-2 py-1 text-xs text-background shadow-md data-[state=delayed-open]:animate-in")}>
          {content}
        </T.Content>
      </T.Portal>
    </T.Root>
  );
}
