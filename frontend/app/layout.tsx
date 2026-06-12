import type { Metadata } from "next";

import { AuthProvider } from "@/components/auth-provider";
import { Header } from "@/components/header";

import "./globals.css";

export const metadata: Metadata = {
  title: "职析 · AI 求职面试助手",
  description: "用 AI 分析简历与岗位匹配度，并生成个性化面试题。",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="zh-CN">
      <body>
        <AuthProvider>
          <Header />
          {children}
        </AuthProvider>
      </body>
    </html>
  );
}
