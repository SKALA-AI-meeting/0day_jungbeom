"use client";

// 리포트 화면. 검토 제출 뒤에는 final이 될 때까지 폴링하고, 오래 끝나지 않으면 같은 본문으로 확정만 다시 시도한다.
import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import { adminApi, errorMessage, useLoad, useToken } from "@/components/admin/client";
import { ReportView } from "@/components/admin/report-view";
import { phaseOf, recordAnchor, reviewBodyFrom } from "@/components/admin/review";
import type { Adjustment } from "@/components/admin/types";
import { Button, Toaster } from "@/components/ui";

const POLL_MS = 2000;
// 이만큼 폴링해도 확정 중이면 "확정만 다시 시도"를 보인다
const STALL_POLLS = 5;
// 연속 조회 실패가 이 횟수에 이르면 폴링을 멈추고 수동 "다시 불러오기"를 보인다
const MAX_FAILURES = 5;

type ReviewBody = { adjustments: Adjustment[]; memo?: string; reviewer_name: string };

export default function ReportPage() {
  const { id } = useParams<{ id: string }>();
  const token = useToken();
  const { data: report, error, failures, reload } = useLoad((t) => adminApi.report(t, id), id);
  const [pending, setPending] = useState(false);
  const [reviewError, setReviewError] = useState<string | null>(null);
  const [polls, setPolls] = useState(0);
  const lastBody = useRef<ReviewBody | null>(null);

  const approving = !!report && phaseOf(report) === "approving";
  const polling = approving && failures < MAX_FAILURES && polls < STALL_POLLS;
  useEffect(() => {
    if (!polling) return;
    const timer = setInterval(() => {
      setPolls((n) => n + 1);
      reload();
    }, POLL_MS);
    return () => clearInterval(timer);
  }, [polling, reload]);

  async function review(body: ReviewBody) {
    if (!token) return;
    setPending(true);
    setReviewError(null);
    lastBody.current = body;
    try {
      await adminApi.review(token, id, body);
      setPolls(0);
      reload();
    } catch (e) {
      setReviewError(errorMessage(e));
    } finally {
      setPending(false);
    }
  }

  return (
    <>
      <div className="no-print flex items-center gap-3 text-sm text-muted">
        <Link href="/admin/positions" className="hover:underline">
          ← 채용 건 목록
        </Link>
        <Link href={`/admin/sessions/${id}/record`} className="ml-auto hover:underline">
          전체 기록 보기
        </Link>
      </div>
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
        <ReportView
          report={report}
          recordHref={(ref, card) =>
            `/admin/sessions/${id}/record${card ? `?card=${card}` : ""}#${recordAnchor(ref)}`
          }
          pending={pending}
          error={reviewError}
          stalled={approving && polls >= STALL_POLLS}
          onReview={review}
          onRetry={() => {
            // 이 화면에서 제출하지 않았으면(재진입) 서버가 저장한 조정·메모·검토자로 같은 본문을 만든다
            const body = lastBody.current ?? reviewBodyFrom(report);
            if (body) void review(body);
          }}
          onAddNote={async (body) => {
            if (!token) return;
            await adminApi.addNote(token, id, body);
            reload();
          }}
        />
      )}
      <Toaster />
    </>
  );
}
