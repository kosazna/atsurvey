import i18n from "i18next";
import { initReactI18next } from "react-i18next";
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

type Tree = { [k: string]: unknown };
function deepMerge<A extends Tree, B extends Tree>(a: A, b: B): A & B {
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

function initialLang(): "el" | "en" {
  try {
    const s = localStorage.getItem("ats-lang");
    if (s === "el" || s === "en") return s;
  } catch {
    /* ignore */
  }
  return "el";
}

void i18n.use(initReactI18next).init({
  resources: {
    el: { translation: [extraEl, securityEl, teamsEl, lifecycleEl, parcelsEl, surfacesEl, setoutEl, coordsEl, analysisEl, instrumentsEl].reduce<Tree>((acc, m) => deepMerge(acc, m), el) },
    en: { translation: [extraEn, securityEn, teamsEn, lifecycleEn, parcelsEn, surfacesEn, setoutEn, coordsEn, analysisEn, instrumentsEn].reduce<Tree>((acc, m) => deepMerge(acc, m), en) },
  },
  lng: initialLang(),
  fallbackLng: "el",
  interpolation: { escapeValue: false },
  returnNull: false,
});

i18n.on("languageChanged", (lng) => {
  try {
    localStorage.setItem("ats-lang", lng);
  } catch {
    /* ignore */
  }
  document.documentElement.lang = lng;
});
document.documentElement.lang = i18n.language;

export function toggleLanguage() {
  void i18n.changeLanguage(i18n.language === "el" ? "en" : "el");
}

export default i18n;
