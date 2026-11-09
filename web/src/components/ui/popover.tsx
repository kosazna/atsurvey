import { Popover as P } from "radix-ui";
import * as React from "react";
import { cn } from "@/lib/utils";

export const Popover = P.Root;
export const PopoverTrigger = P.Trigger;
export const PopoverAnchor = P.Anchor;
export function PopoverContent({ className, sideOffset = 6, align = "start", ...props }: React.ComponentProps<typeof P.Content>) {
  return (
    <P.Portal>
      <P.Content
        sideOffset={sideOffset}
        align={align}
        className={cn("z-(--z-modal) rounded-lg border bg-surface-raised p-3 text-fg shadow-lg outline-none data-[state=open]:animate-in", className)}
        {...props}
      />
    </P.Portal>
  );
}
