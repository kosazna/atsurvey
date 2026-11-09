import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { RouterProvider } from "@tanstack/react-router";
import { Toaster } from "sonner";
import { CommandProvider } from "@/components/commands";
import { TooltipProvider } from "@/components/ui/tooltip";
import { SessionProvider } from "@/data/session";
import { useTheme } from "@/lib/theme";
import { router } from "./router";

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: 1, refetchOnWindowFocus: false, staleTime: 30_000 } },
});

export function App() {
  const theme = useTheme();
  return (
    <QueryClientProvider client={queryClient}>
      <SessionProvider>
        <TooltipProvider>
          <CommandProvider>
            <RouterProvider router={router} />
          </CommandProvider>
        </TooltipProvider>
      </SessionProvider>
      <Toaster theme={theme} position="bottom-right" richColors closeButton />
    </QueryClientProvider>
  );
}
