"use client";

// 샘플 리포트: API가 아니라 web의 정적 픽스처(Report 형식)를 그대로 그린다. 생성 화면·지원자 목록에서 링크한다.
// 주소에 ?print=1이면 인쇄 미리보기(차원 전부 펼침)로 그린다.
import { useSearchParams } from "next/navigation";
import { Suspense } from "react";

import { ReportView } from "@/components/admin/report-view";
import { recordAnchor } from "@/components/admin/review";
import type { Report } from "@/components/admin/types";
import sample from "@/fixtures/sample-report.json";

function SampleReport() {
  const printing = useSearchParams().get("print") === "1";
  return (
    <ReportView
      report={sample as unknown as Report}
      sample
      printing={printing}
      recordHref={(ref) => `/admin/sample-report/record#${recordAnchor(ref)}`}
    />
  );
}

export default function SampleReportPage() {
  return (
    <Suspense>
      <SampleReport />
    </Suspense>
  );
}
