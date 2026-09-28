export type Theme = "dark" | "pink" | "morandi";

const storageKey = "daymark.theme";

export const themeInitScript = `try { document.documentElement.dataset.theme = ["pink", "morandi"].includes(localStorage.getItem("${storageKey}")) ? localStorage.getItem("${storageKey}") : "dark"; } catch { document.documentElement.dataset.theme = "dark"; }`;

export function loadTheme(): Theme {
  let theme: Theme = "dark";
  try {
    const saved = localStorage.getItem(storageKey);
    theme = saved === "pink" || saved === "morandi" ? saved : "dark";
  } catch {}
  document.documentElement.dataset.theme = theme;
  return theme;
}

export function saveTheme(theme: Theme): void {
  document.documentElement.dataset.theme = theme;
  try {
    localStorage.setItem(storageKey, theme);
  } catch {}
}
