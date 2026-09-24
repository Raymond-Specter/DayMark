import type { Metadata } from "next";
import "@fontsource-variable/inter/wght.css";
import "./globals.css";
import "./dark-theme.css";
import "./cinematic-home.css";
export const metadata: Metadata = {
  title: "Daymark · Personal Planning System",
  description: "个人时间规划、任务、日历、重复任务与每日回顾。",
};
export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="zh-CN">
      <body>{children}</body>
    </html>
  );
}
