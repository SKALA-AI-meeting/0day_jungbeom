import type { Metadata, Viewport } from "next";
import type { ReactNode } from "react";

import { DataToggle } from "@/components/dev/data-toggle";
import { MOCK } from "@/lib/api";

// Pretendard(한글)는 패키지에서 자체 호스팅한다. 글자 범위별로 쪼갠 파일이라 쓰는 글자만 받고,
// 못 받으면 globals.css의 시스템 폰트 스택으로 그려진다(오프라인에서도 동작)
import "pretendard/dist/web/variable/pretendardvariable-dynamic-subset.css";
import "./globals.css";

export const metadata: Metadata = {
  title: "Day Zero",
  description: "AI 동료와 함께 일해 보는 협업 시뮬레이션",
  icons: { icon: "/brand/favicon.svg" },
};

// 라이트·다크는 시스템 설정만 따른다(UX 결정 9). 브라우저 UI 색도 canvas에 맞춘다
export const viewport: Viewport = {
  colorScheme: "light dark",
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#f5f5f7" },
    { media: "(prefers-color-scheme: dark)", color: "#000000" },
  ],
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
