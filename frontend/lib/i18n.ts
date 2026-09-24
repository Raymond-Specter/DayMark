import translations from "./ui-translations.json";

const englishUi: Record<string, string> = translations;

export type Language = "en" | "zh";

const storageKey = "daymark.language";
let language: Language = "en";

export function getLanguage(): Language {
  return language;
}

export function browserLocale(): string {
  return language === "en" ? "en-US" : "zh-CN";
}

export function loadLanguage(): Language {
  if (typeof window === "undefined") return language;
  try {
    language = window.localStorage.getItem(storageKey) === "zh" ? "zh" : "en";
  } catch {
    language = "en";
  }
  document.documentElement.lang = language === "en" ? "en" : "zh-CN";
  return language;
}

export function saveLanguage(next: Language): void {
  language = next;
  document.documentElement.lang = next === "en" ? "en" : "zh-CN";
  try {
    window.localStorage.setItem(storageKey, next);
  } catch {
    // The choice still applies for this session when storage is unavailable.
  }
}

export function uiText(source: string): string {
  if (language === "zh") return source;
  return englishUi[source.replace(/\s+/g, " ").trim()] ?? source;
}

export function uiFormat(source: string, ...values: unknown[]): string {
  return uiText(source).replace(/\{(\d+)\}/g, (_, index: string) =>
    String(values[Number(index)] ?? ""),
  );
}
