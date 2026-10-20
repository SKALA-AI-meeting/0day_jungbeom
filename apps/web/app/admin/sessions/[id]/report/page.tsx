"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";

import { adminApi, errorMessage, useLoad, useToken } from "@/components/admin/client";
import { phaseOf } from "@/components/admin/review";
import { ReportView } from "@/components/admin/report-view";
import type { Adjustment } from "@/components/admin/types";
import { Button } from "@/components/ui";

const POLL_MS = 2000;
// 연속 조회 실패가 이 횟수에 이르면 폴링을 멈추고 수동 "다시 불러오기"를 보인다
const MAX_FAILURES = 5;

export default function ReportPage() {
  const { id } = useParams<{ id: string }>();
  const token = useToken();
  const { data: report, error, failures, reload } = useLoad((t) => adminApi.report(t, id), id);
  const [pending, setPending] = useState(false);
  const [reviewError, setReviewError] = useState<string | null>(null);
  const [submitted, setSubmitted] = useState(false);

  // 제출했거나 확정 중(approving)이면 final이 될 때까지 폴링한다. 조회가 실패해도 마지막 리포트는 남는다.
  const waiting = submitted || (!!report && phaseOf(report) === "approving");
  const done = !!report && phaseOf(report) === "final";
  const polling = waiting && !done && failures < MAX_FAILURES;
  useEffect(() => {
    if (!polling) return;
    const timer = setInterval(reload, POLL_MS);
    return () => clearInterval(timer);
  }, [polling, reload]);

  async function review(body: { adjustments: Adjustment[]; memo?: string }) {
    if (!token) return;
    setPending(true);
    setReviewError(null);
    try {
      await adminApi.review(token, id, body);
      setSubmitted(true);
      reload(); // 성공하면 pending은 유지하고, 다시 받은 리포트가 확정 중으로 잠근다
    } catch (e) {
      setReviewError(errorMessage(e));
      setPending(false);
    }
  }

  return (
    <>
      <Link href="/admin/positions" className="text-sm text-muted hover:underline">
        ← 채용 건 목록
      </Link>
      {error && (
        <div role="alert" className="flex items-center gap-3 text-danger">
          <span>{error}</span>
          {failures >= MAX_FAILURES && (
            <Button size="sm" variant="secondary" onClick={reload}>
              다시 불러오기
            </Button>
          )}
        </div>
      )}
      {report && (
        <ReportView report={report} pending={pending} error={reviewError} onReview={review} />
      )}
    </>
  );
}
