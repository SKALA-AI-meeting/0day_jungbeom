"use client";

// 리포트 화면. 검토 제출 뒤에는 final이 될 때까지 폴링하고, 오래 끝나지 않으면 같은 본문으로 확정만 다시 시도한다.
// 주소에 ?print=1이면 인쇄 미리보기(차원 전부 펼침)로 그린다.
import Link from "next/link";
import { useParams, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useRef, useState } from "react";

import { adminApi, errorMessage, useLoad, useToken } from "@/components/admin/client";
import { ReportView } from "@/components/admin/report-view";
import {
  phaseOf,
  recordAnchor,
  REPORT_POLL_MS,
  reportNotReady,
  reviewBodyFrom,
} from "@/components/admin/review";
import type { ReviewBody } from "@/components/admin/types";
import { Button, Toaster } from "@/components/ui";

const POLL_MS = 2000;
// 이만큼 폴링해도 확정 중이면 "확정 다시 시도"를 보인다
const STALL_POLLS = 5;
const MAX_FAILURES = 5;

function ReportPageBody() {
  const { id } = useParams<{ id: string }>();
  const printing = useSearchParams().get("print") === "1";
  const token = useToken();
  const {
    data: report,
    error,
    code,
    failures,
    reload,
  } = useLoad((t) => adminApi.report(t, id), id);
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

  // 리포트가 아직 없으면(draft 생성 전) 안내를 보이고 5초마다 다시 읽는다
  const notReady = !report && reportNotReady(code);
  useEffect(() => {
    if (!notReady) return;
    const timer = setInterval(reload, REPORT_POLL_MS);
    return () => clearInterval(timer);
  }, [notReady, reload]);

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
      // 409 already_reviewed면 최신 리포트를 다시 읽는다
      reload();
    } finally {
      setPending(false);
    }
  }

  return (
    <>
      <div className="no-print mx-auto flex w-full max-w-3xl items-center gap-3 text-sm text-muted">
        <Link href="/admin/positions" className="hover:underline">
          ← 채용 건 목록
        </Link>
        <Link href={`/admin/sessions/${id}/record`} className="ml-auto hover:underline">
          전체 기록 보기
        </Link>
      </div>
      {notReady && (
        <p role="status" className="mx-auto w-full max-w-3xl text-muted">
          리포트를 만드는 중입니다. 준비되면 이 화면에 바로 나타납니다.
        </p>
      )}
      {error && !notReady && (
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
          printing={printing}
          recordHref={(ref) => `/admin/sessions/${id}/record#${recordAnchor(ref)}`}
          pending={pending}
          error={reviewError}
          stalled={approving && polls >= STALL_POLLS}
          onReview={review}
          onRetry={() => {
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

export default function ReportPage() {
  return (
    <Suspense>
      <ReportPageBody />
    </Suspense>
  );
}
