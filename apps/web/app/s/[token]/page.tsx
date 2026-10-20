import type { Metadata } from "next";

import { CandidateFlow } from "@/components/office/candidate-flow";

// 지원자 화면. 단계(입장 → 동의 → 대기 → 오피스 → 디브리핑)는 상태로 전환한다(docs/frontend/design.md).
export const metadata: Metadata = { title: "Day Zero" };

export default async function CandidatePage({ params }: { params: Promise<{ token: string }> }) {
  const { token } = await params;
  return <CandidateFlow token={token} />;
}
