import { Select as S } from "radix-ui";
import { Check, ChevronDown } from "lucide-react";
import * as React from "react";
import { cn } from "@/lib/utils";

export interface SelectOption<V extends string> {
  value: V;
  label: React.ReactNode;
  hint?: React.ReactNode;
}

export function Select<V extends string>({
  value,
  onValueChange,
  options,
  className,
  id,
  placeholder,
  "aria-label": ariaLabel,
}: {
  value: V;
  onValueChange: (v: V) => void;
  options: SelectOption<V>[];
  className?: string;
  id?: string;
  placeholder?: string;
  "aria-label"?: string;
}) {
  return (
    <S.Root value={value} onValueChange={(v) => onValueChange(v as V)}>
      <S.Trigger
        id={id}
        aria-label={ariaLabel}
        className={cn(
          "flex h-8 w-full min-w-0 items-center justify-between gap-2 whitespace-nowrap rounded-md border border-border-strong bg-surface px-2.5 text-left text-sm [&>span:first-child]:truncate focus-visible:border-focus focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-focus/25",
          className,
        )}
      >
        <S.Value placeholder={placeholder} />
        <S.Icon>
          <ChevronDown className="size-4 text-muted" />
        </S.Icon>
      </S.Trigger>
      <S.Portal>
        <S.Content position="popper" sideOffset={4} className="z-(--z-modal) max-h-80 min-w-[var(--radix-select-trigger-width)] overflow-hidden rounded-lg border bg-surface-raised shadow-lg data-[state=open]:animate-in">
          <S.Viewport className="p-1">
            {options.map((o) => (
              <S.Item
                key={o.value}
                value={o.value}
                className="relative flex cursor-pointer select-none flex-col rounded-md py-1.5 pl-7 pr-2 text-sm outline-none data-[highlighted]:bg-surface-sunken"
              >
                <S.ItemIndicator className="absolute left-2 top-2">
                  <Check className="size-3.5" />
                </S.ItemIndicator>
                <S.ItemText>{o.label}</S.ItemText>
                {o.hint && <span className="text-xs text-muted">{o.hint}</span>}
              </S.Item>
            ))}
          </S.Viewport>
        </S.Content>
      </S.Portal>
    </S.Root>
  );
}
