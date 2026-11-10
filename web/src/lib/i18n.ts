import i18n from "i18next";
import { initReactI18next } from "react-i18next";
import { elBundle, enBundle } from "./i18nResources";

/** No-op outside a browser (unit tests import modules that import this one). */
function setDocumentLang(lng: string): void {
  if (typeof document !== "undefined") document.documentElement.lang = lng;
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
    el: { translation: elBundle },
    en: { translation: enBundle },
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
  setDocumentLang(lng);
});
setDocumentLang(i18n.language);

export function toggleLanguage() {
  void i18n.changeLanguage(i18n.language === "el" ? "en" : "el");
}

export default i18n;
