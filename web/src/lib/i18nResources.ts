// Translation bundles: the base files deep-merged with each feature's strings. Pure (no i18next
// side effects) so tests can check that every key exists in both languages.
import el from "@/locales/el";
import en from "@/locales/en";
import extraEl from "@/locales/extra.el";
import extraEn from "@/locales/extra.en";
import securityEl from "@/locales/security.el";
import securityEn from "@/locales/security.en";
import teamsEl from "@/locales/teams.el";
import teamsEn from "@/locales/teams.en";
import lifecycleEl from "@/locales/lifecycle.el";
import lifecycleEn from "@/locales/lifecycle.en";
import parcelsEl from "@/locales/parcels.el";
import parcelsEn from "@/locales/parcels.en";
import surfacesEl from "@/locales/surfaces.el";
import surfacesEn from "@/locales/surfaces.en";
import setoutEl from "@/locales/setout.el";
import setoutEn from "@/locales/setout.en";
import coordsEl from "@/locales/coords.el";
import coordsEn from "@/locales/coords.en";
import analysisEl from "@/locales/analysis.el";
import analysisEn from "@/locales/analysis.en";
import instrumentsEl from "@/locales/instruments.el";
import instrumentsEn from "@/locales/instruments.en";
import dgmEl from "@/locales/dgm.el";
import dgmEn from "@/locales/dgm.en";

export type Tree = { [k: string]: unknown };
export function deepMerge<A extends Tree, B extends Tree>(a: A, b: B): A & B {
  const out: Tree = { ...a };
  for (const [k, v] of Object.entries(b)) {
    const cur = out[k];
    out[k] =
      v && typeof v === "object" && !Array.isArray(v) && cur && typeof cur === "object"
        ? deepMerge(cur as Tree, v as Tree)
        : v;
  }
  return out as A & B;
}

export const elBundle: Tree = [extraEl, securityEl, teamsEl, lifecycleEl, parcelsEl, surfacesEl, setoutEl, coordsEl, analysisEl, instrumentsEl, dgmEl].reduce<Tree>((acc, m) => deepMerge(acc, m), el);
export const enBundle: Tree = [extraEn, securityEn, teamsEn, lifecycleEn, parcelsEn, surfacesEn, setoutEn, coordsEn, analysisEn, instrumentsEn, dgmEn].reduce<Tree>((acc, m) => deepMerge(acc, m), en);
