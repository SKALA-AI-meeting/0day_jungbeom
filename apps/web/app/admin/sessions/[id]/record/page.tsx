"use client";

// 전체 기록 화면(읽기 전용). 리포트 근거의 "기록에서 보기"가 #앵커로 이 화면의 해당 줄을 가리킨다.
import { useParams } from "next/navigation";

import { adminApi, useLoad } from "@/components/admin/client";
import { RecordView } from "@/components/admin/record-view";

export default function RecordPage() {
  const { id } = useParams<{ id: string }>();
  const { data, error } = useLoad((t) => adminApi.record(t, id), id);
  return (
    <>
      <h1 className="text-2xl font-semibold">전체 기록</h1>
      {error && (
        <p role="alert" className="text-danger">
          {error}
        </p>
      )}
      {data && <RecordView entries={data} backHref={`/admin/sessions/${id}/report`} />}
    </>
  );
}
