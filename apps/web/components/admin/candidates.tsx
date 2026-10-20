"use client";

// 채용 건 상세의 지원자 목록과 초대 폼. 상태 묶음 5종(필터 겸용), 세 수 점수, 실패 행동 안내, 삭제 예정일.
import Link from "next/link";
import { useState, type FormEvent } from "react";

import { Button, Card, Chip, cn, ConfirmDialog, EmptyState, Input, toast } from "@/components/ui";

import { countsText, formatDateTime, purgeText } from "./format";
import type { Candidate, DisplayGroup, InviteResult } from "./types";

export const GROUPS: { id: DisplayGroup; label: string }[] = [
  { id: "waiting", label: "대기" },
  { id: "in_progress", label: "진행" },
  { id: "needs_review", label: "검토 필요" },
  { id: "done", label: "완료" },
  { id: "problem", label: "문제" },
];

const STATUS_TEXT: Record<string, string> = {
  invited: "초대됨",
  in_progress: "진행 중",
  reporting: "보고 중",
  completed: "완료",
  report_ready: "리포트 준비됨",
  approving: "확정 중",
  reviewed: "검토 완료",
  failed: "실패",
};

/** 표시 상태. 만료는 접미로("초대됨(만료)"), 시작 뒤 취소는 "중도 종료됨" */
export function statusText(c: Candidate) {
  if (c.display_status === "expired") return "초대됨(만료)";
  if (c.status === "cancelled") return c.started_at ? "중도 종료됨" : "초대됨(취소)";
  if (c.status === "failed") return c.failed_stage === "report" ? "실패(리포트)" : "실패(세션)";
  return STATUS_TEXT[c.status] ?? c.status;
}

/** 재초대(이전 세션과 연결)는 세션 실패·만료·취소에서만 */
export function canReinvite(c: Candidate) {
  return (
    (c.status === "failed" && c.failed_stage === "session") ||
    c.display_status === "expired" ||
    c.status === "cancelled"
  );
}

export const canRegenerate = (c: Candidate) => c.status === "failed" && c.failed_stage === "report";
export const canCancel = (c: Candidate) =>
  c.display_status !== "expired" && ["invited", "in_progress", "reporting"].includes(c.status);
const hasReport = (c: Candidate) => ["report_ready", "approving", "reviewed"].includes(c.status);

const GROUP_TONE: Record<DisplayGroup, "neutral" | "accent" | "warning" | "success" | "danger"> = {
  waiting: "neutral",
  in_progress: "accent",
  needs_review: "warning",
  done: "success",
  problem: "danger",
};

export type CandidateTableProps = {
  candidates: Candidate[];
  names: Map<string, string>;
  onCancel: (candidate: Candidate) => void;
  onReinvite: (candidate: Candidate) => void;
  onRegenerate: (candidate: Candidate) => void;
};

function Row({
  c,
  names,
  onAsk,
  onReinvite,
  onRegenerate,
}: {
  c: Candidate;
  names: Map<string, string>;
  onAsk: (c: Candidate) => void;
  onReinvite: (c: Candidate) => void;
  onRegenerate: (c: Candidate) => void;
}) {
  const purge = purgeText(c.purge_at);
  return (
    <li className="flex flex-col gap-2 py-4">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
        <span className="min-w-0 font-semibold break-all">{c.alias}</span>
        <Chip tone={GROUP_TONE[c.display_group]}>{statusText(c)}</Chip>
        {c.previous_relation && (
          <Chip tone="outline">{c.previous_relation === "retry" ? "재응시" : "초대 연장"}</Chip>
        )}
        <span className="min-w-0 text-sm break-all text-muted">{c.email}</span>
        <span className="ml-auto flex shrink-0 items-center gap-2">
          {hasReport(c) && (
            <Link href={`/admin/sessions/${c.session_id}/report`}>
              <Button size="sm" variant={c.status === "report_ready" ? "primary" : "secondary"}>
                리포트
              </Button>
            </Link>
          )}
          {canReinvite(c) && (
            <Button size="sm" variant="secondary" onClick={() => onReinvite(c)}>
              {c.display_status === "expired" ? "초대 연장" : "다시 초대"}
            </Button>
          )}
          {canRegenerate(c) && (
            <Button size="sm" variant="secondary" onClick={() => onRegenerate(c)}>
              리포트 다시 생성
            </Button>
          )}
          {canCancel(c) && (
            <Button size="sm" variant="ghost" onClick={() => onAsk(c)}>
              {c.status === "invited" ? "초대 취소" : "중도 종료"}
            </Button>
          )}
        </span>
      </div>
      <div className="flex flex-wrap gap-x-4 gap-y-1 text-sm text-muted">
        <span>{formatDateTime(c.invited_at)} 초대</span>
        {c.started_at && (
          <span>
            {formatDateTime(c.started_at)} 시작 · {formatDateTime(c.ends_at)}{" "}
            {["in_progress", "reporting"].includes(c.status) ? "종료 예정" : "종료"}
          </span>
        )}
        {c.last_activity_at && <span>마지막 활동 {formatDateTime(c.last_activity_at)}</span>}
        <span>메시지 {c.message_count}개</span>
        {purge && <span>{purge}</span>}
      </div>
      {c.next_action && (
        <p className="rounded-md bg-danger-soft px-3 py-2 text-sm text-ink">
          <b className="font-semibold text-danger">할 일 </b>
          {c.next_action}
        </p>
      )}
      {c.met != null && c.unmet != null && c.no_record != null && (
        <div className="flex flex-col gap-1.5">
          <p className="text-sm">
            <span className="font-medium tabular-nums">
              {countsText({ met: c.met, unmet: c.unmet, no_record: c.no_record })}
            </span>
            <span className="text-muted">
              {" "}
              · {c.score_source === "reviewer" ? "담당자 확정 값" : "기본 값(검토 전)"}
            </span>
          </p>
          {c.by_element && (
            <ul className="flex flex-wrap items-center gap-1.5">
              <li className="text-xs text-subtle">요소별 충족·미충족·기록 없음</li>
              {c.by_element.map((e) => (
                <li key={e.element}>
                  <Chip tone="outline">
                    {names.get(e.element) ?? e.element} {e.met}·{e.unmet}·{e.no_record}
                  </Chip>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </li>
  );
}

export function CandidateTable({
  candidates,
  names,
  onCancel,
  onReinvite,
  onRegenerate,
}: CandidateTableProps) {
  const [filter, setFilter] = useState<DisplayGroup | "all">("all");
  const [target, setTarget] = useState<Candidate | null>(null);

  if (candidates.length === 0) {
    return (
      <EmptyState
        title="아직 초대한 지원자가 없습니다"
        description="아래 초대 폼에서 링크 만들기"
      />
    );
  }
  const count = (g: DisplayGroup) => candidates.filter((c) => c.display_group === g).length;
  const groups = GROUPS.filter((g) => filter === "all" || g.id === filter);

  return (
    <>
      <div role="group" aria-label="상태 필터" className="mb-2 flex flex-wrap gap-1.5">
        {[{ id: "all" as const, label: "전체" }, ...GROUPS].map((g) => (
          <button
            key={g.id}
            type="button"
            aria-pressed={filter === g.id}
            onClick={() => setFilter(g.id)}
            className={cn(
              "press rounded-md border px-2.5 py-1 text-sm",
              filter === g.id
                ? "border-accent bg-accent-soft text-accent-strong"
                : "border-line bg-surface text-muted hover:bg-surface-sunken",
            )}
          >
            {g.label}{" "}
            <span className="tabular-nums">{g.id === "all" ? candidates.length : count(g.id)}</span>
          </button>
        ))}
      </div>
      <p className="mb-2 text-sm text-muted">
        점수: 충족·미충족·기록 없음 세 수 · 요소 구성이 같으면 같은 기준 · 정렬·순위 없음
      </p>
      {groups.map((g) => {
        const rows = candidates.filter((c) => c.display_group === g.id);
        if (rows.length === 0)
          return filter === "all" ? null : (
            <EmptyState key={g.id} title={`${g.label} 지원자 없음`} />
          );
        return (
          <section key={g.id} className="border-t border-line pt-3 first-of-type:border-t-0">
            <h3 className="text-sm font-semibold text-muted">
              {g.label} <span className="tabular-nums">{rows.length}</span>
            </h3>
            <ul className="flex flex-col divide-y divide-line">
              {rows.map((c) => (
                <Row
                  key={c.session_id}
                  c={c}
                  names={names}
                  onAsk={setTarget}
                  onReinvite={onReinvite}
                  onRegenerate={onRegenerate}
                />
              ))}
            </ul>
          </section>
        );
      })}
      <ConfirmDialog
        open={target != null}
        onOpenChange={(open) => !open && setTarget(null)}
        title={target?.status === "invited" ? "초대를 취소할까요?" : "진행 중인 세션을 끝낼까요?"}
        description={
          target?.status === "invited"
            ? "링크가 더 이상 열리지 않습니다."
            : "세션이 바로 끝나고 리포트는 만들지 않습니다(중도 포기)."
        }
        cancelLabel="돌아가기"
        confirmLabel={target?.status === "invited" ? "초대 취소" : "세션 끝내기"}
        tone="danger"
        onConfirm={() => {
          if (target) onCancel(target);
          setTarget(null);
        }}
      />
    </>
  );
}

export type InvitePrefill = {
  alias: string;
  previous_session_id: string;
  email: string;
  relation: string;
};

export type InvitePanelProps = {
  prefill: InvitePrefill | null;
  /** 같은 채용 건 안에서 이미 쓴 별칭(제출 전에 막는다) */
  takenAliases: string[];
  onClearPrefill: () => void;
  pending?: boolean;
  error?: string | null;
  result: InviteResult | null;
  onInvite: (value: { alias: string; email: string; previous_session_id?: string }) => void;
};

async function copy(text: string, what: string) {
  try {
    await navigator.clipboard.writeText(text);
    toast(`${what}를 복사했어요`);
  } catch {
    // 클립보드 권한이 없으면 화면의 글을 직접 선택하게 둔다
    toast(`${what}를 복사하지 못했어요. 직접 선택해 주세요.`);
  }
}

export function InvitePanel({
  prefill,
  takenAliases,
  onClearPrefill,
  pending,
  error,
  result,
  onInvite,
}: InvitePanelProps) {
  const [alias, setAlias] = useState(prefill?.alias ?? "");
  const [email, setEmail] = useState(prefill?.email ?? "");
  const duplicate = !prefill && takenAliases.includes(alias.trim());
  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (duplicate) return;
    onInvite({
      alias: alias.trim(),
      email: email.trim(),
      ...(prefill ? { previous_session_id: prefill.previous_session_id } : {}),
    });
  };
  return (
    <Card title={prefill ? `${prefill.alias} ${prefill.relation}` : "지원자 초대"}>
      <form className="flex flex-col gap-4" onSubmit={submit}>
        {prefill && (
          <p className="flex items-center gap-2 text-sm text-muted">
            이전 세션과 연결한 새 링크
            <button type="button" className="text-accent hover:underline" onClick={onClearPrefill}>
              새 지원자로 바꾸기
            </button>
          </p>
        )}
        <div className="grid gap-4 md:grid-cols-2">
          <Input
            label="별칭"
            value={alias}
            readOnly={!!prefill}
            onChange={(e) => setAlias(e.target.value)}
            hint="지원자 안내·세션·리포트에 쓰이는 이름"
            error={duplicate ? "이미 있는 별칭" : undefined}
            required
          />
          <Input
            label="이메일"
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
          />
        </div>
        {error && (
          <p role="alert" className="text-sm text-danger">
            {error}
          </p>
        )}
        <div>
          <Button type="submit" loading={pending} disabled={duplicate}>
            초대 링크 만들기
          </Button>
        </div>
      </form>
      {result && (
        <div className="mt-5 flex flex-col gap-3 border-t border-line pt-4">
          <p className="text-sm text-muted">
            자동 발송 없음 · 복사해서 전달 · {formatDateTime(result.expires_at)} 만료(72시간)
          </p>
          <div className="flex flex-wrap items-center gap-2">
            <code className="min-w-0 flex-1 rounded-md bg-surface-sunken px-3 py-2 text-sm break-all">
              {result.invite_url}
            </code>
            <Button
              size="sm"
              variant="secondary"
              onClick={() => void copy(result.invite_url, "링크")}
            >
              링크 복사
            </Button>
            <Button
              size="sm"
              variant="secondary"
              onClick={() => void copy(result.notice_text, "안내 문안")}
            >
              안내 문안 복사
            </Button>
          </div>
        </div>
      )}
    </Card>
  );
}
