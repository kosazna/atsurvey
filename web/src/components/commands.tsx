import { createContext, useContext, useEffect, useMemo, useState } from "react";

export interface Command {
  id: string;
  group: string;
  label: string;
  icon?: React.ReactNode;
  shortcut?: string;
  keywords?: string[];
  run: () => void;
}

interface Ctx {
  page: Command[];
  setPage: (c: Command[]) => void;
  open: boolean;
  setOpen: (o: boolean) => void;
}

const CommandCtx = createContext<Ctx | null>(null);

export function CommandProvider({ children }: { children: React.ReactNode }) {
  const [page, setPage] = useState<Command[]>([]);
  const [open, setOpen] = useState(false);
  const value = useMemo(() => ({ page, setPage, open, setOpen }), [page, open]);
  return <CommandCtx.Provider value={value}>{children}</CommandCtx.Provider>;
}

export function useCommandCtx() {
  const c = useContext(CommandCtx);
  if (!c) throw new Error("CommandProvider missing");
  return c;
}

/** Register page-specific commands while the component is mounted. */
export function usePageCommands(commands: Command[]) {
  const { setPage } = useCommandCtx();
  useEffect(() => {
    setPage(commands);
    return () => setPage([]);
  }, [commands, setPage]);
}
