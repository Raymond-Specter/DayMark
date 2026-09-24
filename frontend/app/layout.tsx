import type { Metadata } from "next";
import "@fontsource-variable/inter/wght.css";
import "./globals.css";
import "./dark-theme.css";
import "./cinematic-home.css";
export const metadata: Metadata = {
  title: "Daymark · Personal Planning System",
  description: "Personal planning for tasks, calendars, routines, and daily reviews.",
};
export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
