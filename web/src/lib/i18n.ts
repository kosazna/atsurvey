import i18n from "i18next";
import { initReactI18next } from "react-i18next";
import el from "@/locales/el";
import en from "@/locales/en";

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
  resources: { el: { translation: el }, en: { translation: en } },
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
