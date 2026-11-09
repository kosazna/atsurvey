import * as React from "react";
import { cn } from "@/lib/utils";

export const Input = React.forwardRef<HTMLInputElement, React.InputHTMLAttributes<HTMLInputElement>>(
  ({ className, type, ...props }, ref) => (
    <input
      ref={ref}
      type={type}
      className={cn(
        "flex h-8 w-full min-w-0 rounded-md border border-border-strong bg-surface px-2.5 text-sm transition-colors placeholder:text-subtle focus-visible:border-focus focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-focus/25 disabled:opacity-50 aria-invalid:border-danger",
        className,
      )}
      {...props}
    />
  ),
);
Input.displayName = "Input";

export const Textarea = React.forwardRef<HTMLTextAreaElement, React.TextareaHTMLAttributes<HTMLTextAreaElement>>(
  ({ className, ...props }, ref) => (
    <textarea
      ref={ref}
      className={cn(
        "flex min-h-16 w-full rounded-md border border-border-strong bg-surface px-2.5 py-1.5 text-sm placeholder:text-subtle focus-visible:border-focus focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-focus/25",
        className,
      )}
      {...props}
    />
  ),
);
Textarea.displayName = "Textarea";
