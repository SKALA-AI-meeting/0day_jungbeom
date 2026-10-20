import type { Metadata } from "next";
import type { ReactNode } from "react";

import { DataToggle } from "@/components/dev/data-toggle";
import { MOCK } from "@/lib/api";

import "./globals.css";

export const metadata: Metadata = {
  title: "Day Zero",
  description: "AI 동료와 함께 일해 보는 협업 시뮬레이션",
  icons: { icon: "/brand/favicon.svg" },
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="ko">
      <body>
        {children}
        {/* 개발 mock에서만: break-ui 점검용 Demo / Worst case 데이터 전환 */}
        {MOCK && <DataToggle />}
      </body>
    </html>
  );
}
