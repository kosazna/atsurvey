import {
  ArrowDownUp,
  Crosshair,
  FileText,
  Flag,
  Globe,
  History,
  LandPlot,
  LayoutDashboard,
  ListOrdered,
  Mountain,
  Network,
  Route as RouteIcon,
  ScrollText,
  ShieldCheck,
  Sigma,
  Spline,
  Telescope,
  Triangle,
  Wrench,
} from "lucide-react";
import type { ReactNode } from "react";
import { SECTION_GROUP, SECTIONS, type NavGroup, type Section } from "./sections";

export const SECTION_ICONS: Record<Section, ReactNode> = {
  overview: <LayoutDashboard />,
  control: <Triangle />,
  observations: <Telescope />,
  traverses: <RouteIcon />,
  leveling: <ArrowDownUp />,
  results: <ListOrdered />,
  adjustment: <Sigma />,
  linework: <Spline />,
  reports: <FileText />,
  issues: <ShieldCheck />,
  runs: <History />,
  parcels: <LandPlot />,
  cadastre: <ScrollText />,
  terrain: <Mountain />,
  setout: <Flag />,
  cogo: <Crosshair />,
  coords: <Globe />,
  preanalysis: <Network />,
  instruments: <Wrench />,
};

export interface NavItem {
  id: Section;
  icon: ReactNode;
  group: NavGroup | null;
}

/** Sidebar entries in display order (SECTIONS order), grouped by SECTION_GROUP. */
export const NAV: NavItem[] = SECTIONS.map((id) => ({ id, icon: SECTION_ICONS[id], group: SECTION_GROUP[id] }));
