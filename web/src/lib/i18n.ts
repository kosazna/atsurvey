import i18n from "i18next";
import { initReactI18next } from "react-i18next";
import el from "@/locales/el";
import en from "@/locales/en";
import extraEl from "@/locales/extra.el";
import extraEn from "@/locales/extra.en";
import securityEl from "@/locales/security.el";
import securityEn from "@/locales/security.en";

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
    el: { translation: deepMerge(deepMerge(el, extraEl), securityEl) },
    en: { translation: deepMerge(deepMerge(en, extraEn), securityEn) },
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
