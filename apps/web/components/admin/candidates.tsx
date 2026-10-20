"use client";

import Link from "next/link";
import { useState, type FormEvent } from "react";

import { Button, Card, ConfirmDialog, EmptyState, Input, StatusBadge } from "@/components/ui";

import { formatDateTime } from "./format";
import { ScoreChips, ScoreTotal } from "./score";
import type { Candidate, InviteResult } from "./types";

export type CandidateTableProps = {
  candidates: Candidate[];
  /** 요소 id → 표시 이름 */
  names: Map<string, string>;
  onCancel: (candidate: Candidate) => void;
  /** 실패·만료·취소·리포트 없는 완료 지원자를 같은 별칭으로 다시 초대 */
  onReinvite: (candidate: Candidate) => void;
};

/** 재초대 대상: 응시가 끝나지 못했거나 리포트 없이 끝난 행(PRD F-02) */
export function canReinvite(c: Candidate): boolean {
  return (
    c.status === "failed" ||
    c.status === "cancelled" ||
    c.display_status === "expired" ||
    (c.status === "completed" && !c.score)
  );
}

export function CandidateTable({ candidates, names, onCancel, onReinvite }: CandidateTableProps) {
  const [target, setTarget] = useState<Candidate | null>(null);

  if (candidates.length === 0) {
    return (
      <EmptyState
        title="아직 초대한 지원자가 없습니다"
        description="아래 폼에서 초대 링크를 만드세요."
      />
    );
  }
  return (
    <>
      <p className="mb-3 text-sm text-muted">
        기록 없음은 분모에서 빠지므로 비율만으로 지원자를 비교하지 않습니다. 점수 정렬은 없습니다.
      </p>
      <ul className="flex flex-col divide-y divide-line">
        {candidates.map((candidate) => (
          <li key={candidate.session_id} className="flex flex-col gap-2 py-3">
            <div className="flex flex-wrap items-center gap-3">
              <span className="font-medium">{candidate.alias}</span>
              <StatusBadge status={candidate.display_status} />
              {candidate.previous_session_id && <span className="text-sm text-muted">재응시</span>}
              <span className="text-sm text-subtle">
                {formatDateTime(candidate.invited_at)} 초대
              </span>
              <span className="ml-auto flex items-center gap-2">
                {candidate.score && (
                  <Link href={`/admin/sessions/${candidate.session_id}/report`}>
                    <Button size="sm" variant="secondary">
                      리포트
                    </Button>
                  </Link>
                )}
                {canReinvite(candidate) && (
                  <Button size="sm" variant="secondary" onClick={() => onReinvite(candidate)}>
                    다시 초대
                  </Button>
                )}
                {candidate.status === "invited" && (
                  <Button size="sm" variant="ghost" onClick={() => setTarget(candidate)}>
                    초대 취소
                  </Button>
                )}
              </span>
            </div>
            {candidate.score && (
              <div className="flex flex-wrap items-center gap-3">
                <ScoreTotal score={candidate.score} />
                <ScoreChips score={candidate.score} names={names} />
              </div>
            )}
            {candidate.failed_stage && (
              <p className="text-sm text-danger">
                {candidate.failed_stage === "report" ? "리포트 생성 실패" : "세션 실패"}
                {candidate.failed_reason ? `: ${candidate.failed_reason}` : ""}
              </p>
            )}
          </li>
        ))}
      </ul>
      <ConfirmDialog
        open={target !== null}
        onOpenChange={(open) => !open && setTarget(null)}
        title={`${target?.alias ?? ""} 초대를 취소할까요?`}
        description="취소하면 이 링크로는 입장할 수 없습니다."
        confirmLabel="초대 취소"
        tone="danger"
        onConfirm={() => {
          if (target) onCancel(target);
          setTarget(null);
        }}
      />
    </>
  );
}

/** 다시 초대 시 채워 둘 값. previous_session_id는 요청에 함께 보낸다. */
export type InvitePrefill = { alias: string; previous_session_id: string };

export type InvitePanelProps = {
  prefill?: InvitePrefill | null;
  onClearPrefill?: () => void;
  pending?: boolean;
  error?: string | null;
  /** 직전에 만든 초대. 링크와 안내 문안 복사 버튼을 보여 준다. */
  result?: InviteResult | null;
  onInvite: (value: { alias: string; email: string; previous_session_id?: string }) => void;
};

async function copy(text: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    return false;
  }
}

function CopyButton({ label, text }: { label: string; text: string }) {
  const [state, setState] = useState<"idle" | "done" | "failed">("idle");
  return (
    <Button
      size="sm"
      variant="secondary"
      onClick={async () => setState((await copy(text)) ? "done" : "failed")}
    >
      {state === "done" ? "복사됨" : state === "failed" ? "복사 실패: 직접 선택하세요" : label}
    </Button>
  );
}

export function InvitePanel({
  prefill,
  onClearPrefill,
  pending,
  error,
  result,
  onInvite,
}: InvitePanelProps) {
  const [alias, setAlias] = useState(prefill?.alias ?? "");
  const [email, setEmail] = useState("");

  function submit(event: FormEvent) {
    event.preventDefault();
    onInvite({
      alias: alias.trim(),
      email: email.trim(),
      ...(prefill && { previous_session_id: prefill.previous_session_id }),
    });
  }

  return (
    <Card title="지원자 초대">
      <form className="flex flex-col gap-4 sm:flex-row sm:items-end" onSubmit={submit}>
        <div className="flex-1">
          <Input label="별칭" value={alias} onChange={(e) => setAlias(e.target.value)} required />
        </div>
        <div className="flex-1">
          <Input
            label="이메일"
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
          />
        </div>
        <Button type="submit" loading={pending}>
          초대 링크 만들기
        </Button>
      </form>
      {prefill && (
        <p className="mt-3 text-sm text-muted">
          이전 응시와 연결해 재응시로 초대합니다.{" "}
          <button type="button" className="underline" onClick={onClearPrefill}>
            연결 해제
          </button>
        </p>
      )}
      {error && (
        <p role="alert" className="mt-3 text-sm text-danger">
          {error}
        </p>
      )}
      {result && (
        <div className="mt-4 flex flex-col gap-2 rounded-md bg-surface-sunken p-4">
          <p className="text-sm text-muted">
            이메일은 발송되지 않습니다. 링크나 안내 문안을 복사해 직접 전달하세요. 링크는{" "}
            {formatDateTime(result.expires_at)}까지 유효합니다.
          </p>
          <code className="break-all font-mono text-sm">{result.invite_url}</code>
          <div className="flex gap-2">
            <CopyButton label="링크 복사" text={result.invite_url} />
            <CopyButton label="안내 문안 복사" text={result.notice_text} />
          </div>
        </div>
      )}
    </Card>
  );
}
