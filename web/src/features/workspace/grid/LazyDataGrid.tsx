import { lazy } from "react";
import type DataGridType from "./DataGrid";

// React.lazy erases generics; re-type it as the generic component.
export const DataGrid = lazy(() => import("./DataGrid")) as unknown as typeof DataGridType;
