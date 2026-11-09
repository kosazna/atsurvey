import { Checkbox as C } from "radix-ui";
import { Check } from "lucide-react";
import * as React from "react";
import { cn } from "@/lib/utils";

export function Checkbox({ className, ...props }: React.ComponentProps<typeof C.Root>) {
  return (
    <C.Root
      className={cn(
        "peer size-4 shrink-0 cursor-pointer rounded-[4px] border border-input bg-card shadow-xs data-[state=checked]:border-primary data-[state=checked]:bg-primary data-[state=checked]:text-primary-foreground",
        className,
      )}
      {...props}
    >
      <C.Indicator className="flex items-center justify-center">
        <Check className="size-3" strokeWidth={3} />
      </C.Indicator>
    </C.Root>
  );
}
