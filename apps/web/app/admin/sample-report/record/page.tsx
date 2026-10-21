"use client";

// 샘플 리포트의 전체 기록(정적 픽스처). record_ref는 sample-report.json과 같은 값이다.
import { RecordView } from "@/components/admin/record-view";
import type { RecordEntry, Report } from "@/components/admin/types";
import sample from "@/fixtures/sample-report.json";
import record from "@/mocks/fixtures/admin_record.json";

export default function SampleRecordPage() {
  const report = sample as unknown as Report;
  return (
    <div className="mx-auto flex w-full max-w-3xl flex-col gap-4">
      <h1 className="text-title1 font-bold">전체 기록 (샘플)</h1>
      <RecordView
        entries={record as RecordEntry[]}
        seats={report.seats}
        sessionMinutes={report.position.session_minutes}
        backHref="/admin/sample-report"
      />
    </div>
  );
}
