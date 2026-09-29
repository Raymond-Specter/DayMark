import type { Metadata } from "next";
import "@fontsource-variable/inter/wght.css";
import "./globals.css";
import "./dark-theme.css";
import "./cinematic-home.css";
import "./pink-theme.css";
import "./morandi-theme.css";
import "./mist-theme.css";
import { themeInitScript } from "@/lib/theme";
import AccountGate from "@/components/AccountGate";
import "./account.css";
export const metadata: Metadata = {
  title: "Daymark · Personal Planning System",
  description: "Personal planning for tasks, calendars, routines, and daily reviews.",
};
export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head><script dangerouslySetInnerHTML={{ __html: themeInitScript }} /></head>
      <body><AccountGate>{children}</AccountGate></body>
    </html>
  );
}
