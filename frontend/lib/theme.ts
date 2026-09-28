export type Theme = "dark" | "pink";

const storageKey = "daymark.theme";

export const themeInitScript = `try { document.documentElement.dataset.theme = localStorage.getItem("${storageKey}") === "pink" ? "pink" : "dark"; } catch { document.documentElement.dataset.theme = "dark"; }`;

export function loadTheme(): Theme {
  let theme: Theme = "dark";
  try {
    theme = localStorage.getItem(storageKey) === "pink" ? "pink" : "dark";
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
