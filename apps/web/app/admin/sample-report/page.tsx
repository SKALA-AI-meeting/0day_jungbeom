"use client";

// 샘플 리포트: API가 아니라 web의 정적 픽스처(Report 형식)를 그대로 그린다. 생성 화면·지원자 목록에서 링크한다.
import { ReportView } from "@/components/admin/report-view";
import { recordAnchor } from "@/components/admin/review";
import type { Report } from "@/components/admin/types";
import sample from "@/mocks/fixtures/report.json";

export default function SampleReportPage() {
  return (
    <ReportView
      report={sample as unknown as Report}
      sample
      recordHref={(ref, card) =>
        `/admin/sample-report/record${card ? `?card=${card}` : ""}#${recordAnchor(ref)}`
      }
    />
  );
}
