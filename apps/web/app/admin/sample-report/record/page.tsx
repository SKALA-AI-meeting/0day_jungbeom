"use client";

// 샘플 리포트의 전체 기록(정적 픽스처).
import { RecordView } from "@/components/admin/record-view";
import type { RecordEntry } from "@/components/admin/types";
import record from "@/mocks/fixtures/admin_record.json";

export default function SampleRecordPage() {
  return (
    <>
      <h1 className="text-2xl font-semibold">전체 기록 (샘플)</h1>
      <RecordView entries={record as RecordEntry[]} backHref="/admin/sample-report" />
    </>
  );
}
