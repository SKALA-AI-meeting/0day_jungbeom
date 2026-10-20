"use client";

import { useState } from "react";

import { Badge, Button, Card, Select, Textarea } from "@/components/ui";

import { formatDateTime, NO_RECORD_REASONS, tallyText } from "./format";
import {
  changedAdjustments,
  missingMemos,
  phaseOf,
  previewTotal,
  type Choice,
  type Draft,
} from "./review";
import type {
  Adjustment,
  AiEvidence,
  Evidence,
  Fact,
  ItemValue,
  Report,
  ReportSection,
  RubricElement,
  RubricItem,
} from "./types";

export const REPORT_NOTICE =
  "기본 점수는 관찰 기록을 평가표 규칙에 대입해 자동 계산한 값이고 담당자 점수는 검토자가 근거를 보고 조정한 값이며, 이 리포트는 합격·불합격을 판정하지 않습니다";

const PHASE_BADGE = {
  draft: { tone: "warning", label: "검토 대기 · draft" },
  approving: { tone: "warning", label: "확정 중" },
  final: { tone: "success", label: "검토 완료 · final" },
} as const;

const ASSIGNEE: Record<string, string> = { candidate: "지원자", colleague: "동료", both: "공동" };
const DECIDED_BY: Record<string, string> = {
  candidate: "리드(지원자)가 정함",
  colleague_default: "정하지 않아 기본안으로 진행",
};
const CHOICES: { value: Choice; label: string }[] = [
  { value: "keep", label: "자동 값 유지" },
  { value: "1", label: "충족" },
  { value: "0", label: "미충족" },
  { value: "null", label: "기록 없음" },
];

const minutes = (t: number) => `${Math.round(t * 10) / 10}분`;
const valueLabel = (value: ItemValue) =>
  value === 1 ? "충족" : value === 0 ? "미충족" : "기록 없음";
const factText = (fact: Fact) => (typeof fact === "string" ? fact : fact.text);

/** 카드 발생 시각: 섹션 값이 있으면 그것, 없으면 근거의 context.card_at_t_min(계약) */
function cardTime(section: ReportSection): number | undefined {
  if (section.card_t_min !== undefined) return section.card_t_min;
  return (
    section.evidence.find((e) => e.context?.card_at_t_min != null)?.context?.card_at_t_min ??
    undefined
  );
}

function EvidenceLine({ evidence }: { evidence: Evidence }) {
  const when = <span className="text-subtle">{minutes(evidence.t_min)}</span>;
  if (evidence.type === "message") {
    return (
      <li className="flex flex-col gap-0.5">
        <span>
          {when} · {evidence.channel === "dm" ? "DM" : "팀 채널"} “{evidence.quote}”
        </span>
        {evidence.context?.prev_persona_message && (
          <span className="text-sm text-muted">
            직전 메시지: {evidence.context.prev_persona_message}
          </span>
        )}
      </li>
    );
  }
  if (evidence.type === "revision") {
    return (
      <li>
        {when} · {evidence.summary ?? `${evidence.part_no}번 파트 수정`}
      </li>
    );
  }
  if (evidence.type === "doc_view") {
    return (
      <li>
        {when} · {evidence.summary ?? "문서 열람"}
      </li>
    );
  }
  return (
    <li>
      {when} · 어시스턴트 호출 {evidence.quote ? `“${evidence.quote}”` : ""}
    </li>
  );
}

function Deliverable({ report }: { report: Report }) {
  const {
    parts,
    division_decided_by: decidedBy,
    final_report_message: finalMessage,
  } = report.deliverable;
  return (
    <Card title="① 산출물">
      <p className="mb-3 text-sm text-muted">
        기획안 최종본입니다. 산출물 품질은 점수에 반영되지 않습니다.
        {decidedBy && ` 분업: ${DECIDED_BY[decidedBy] ?? decidedBy}.`}
      </p>
      <ol className="flex flex-col gap-4">
        {parts.map((part) => (
          <li key={part.part_no} className="flex flex-col gap-1.5">
            <div className="flex flex-wrap items-center gap-2">
              <span className="font-medium">
                {part.part_no}. {part.title}
              </span>
              <Badge tone={part.assignee === "colleague" ? "neutral" : "accent"}>
                {ASSIGNEE[part.assignee ?? ""] ?? "미정"}
              </Badge>
              <span className="text-sm text-subtle">수정 {part.revisions}회</span>
              {part.empty && <Badge tone="warning">미작성</Badge>}
            </div>
            {!part.empty && (
              <p className="whitespace-pre-wrap rounded-md bg-surface-sunken p-3 text-sm">
                {part.content}
              </p>
            )}
          </li>
        ))}
      </ol>
      {finalMessage && (
        <div className="mt-4 border-t border-line pt-3">
          <p className="mb-1 text-sm font-medium">
            최종 보고 메시지 <span className="text-subtle">{minutes(finalMessage.t_min)}</span>
          </p>
          <p className="whitespace-pre-wrap text-sm">{finalMessage.content}</p>
        </div>
      )}
    </Card>
  );
}

type ItemRowProps = {
  item: RubricItem;
  sectionReason?: string;
  locked: boolean;
  entry: { choice: Choice; memo: string };
  memoMissing: boolean;
  onChange: (next: { choice: Choice; memo: string }) => void;
};

function ItemRow({ item, sectionReason, locked, entry, memoMissing, onChange }: ItemRowProps) {
  const reason = item.no_record_reason ?? sectionReason;
  const changed = entry.choice !== "keep" && entry.choice !== String(item.auto);
  return (
    <li className="flex flex-col gap-2 rounded-md border border-line p-3">
      <div className="flex flex-wrap items-center gap-2">
        <span className="flex-1">{item.text}</span>
        <Badge tone={item.auto === 1 ? "success" : item.auto === 0 ? "danger" : "neutral"}>
          자동 {valueLabel(item.auto)}
        </Badge>
        {item.auto === null && reason && (
          <span className="text-sm text-muted">{NO_RECORD_REASONS[reason] ?? reason}</span>
        )}
        {item.minutes !== undefined && (
          <span className="text-sm text-muted">실제 {item.minutes}분</span>
        )}
      </div>
      {item.evidence.length > 0 && (
        <p className="text-sm text-subtle">
          근거 {item.evidence.length}건 (
          {item.evidence.map((e) => (e.t_min === undefined ? e.type : minutes(e.t_min))).join(", ")}
          )
        </p>
      )}
      {locked ? (
        item.adjusted && (
          <p className="text-sm">
            <Badge tone="success">담당자 {valueLabel(item.reviewer)}</Badge>{" "}
            <span className="text-muted">메모: {item.memo}</span>
          </p>
        )
      ) : (
        <div className="flex flex-col gap-2 sm:flex-row sm:items-start">
          <div className="sm:w-44">
            <Select
              label="담당자 값"
              value={entry.choice}
              options={CHOICES}
              onChange={(e) => onChange({ ...entry, choice: e.target.value as Choice })}
            />
          </div>
          {changed && (
            <div className="flex-1">
              <Textarea
                label="메모 (필수)"
                value={entry.memo}
                error={memoMissing ? "값을 바꾼 항목에는 메모가 필요합니다." : undefined}
                onChange={(e) => onChange({ ...entry, memo: e.target.value })}
              />
            </div>
          )}
        </div>
      )}
    </li>
  );
}

type ElementCardProps = {
  section: ReportSection;
  rubric: RubricElement | undefined;
  locked: boolean;
  draft: Draft;
  missing: Set<string>;
  onChange: (itemId: string, next: { choice: Choice; memo: string }) => void;
};

function ElementCard({ section, rubric, locked, draft, missing, onChange }: ElementCardProps) {
  const memos = rubric?.items.filter((i) => i.adjusted && i.memo) ?? [];
  const cardAt = cardTime(section);
  const memoLines = memos.map((item) => (
    <p key={item.id} className="text-sm text-muted">
      담당자 메모({item.text}): {item.memo}
    </p>
  ));
  return (
    <Card
      title={section.name}
      actions={
        rubric && (
          <span className="text-sm text-muted">
            기본 {tallyText(rubric.auto)}
            {rubric.reviewer && ` · 담당자 ${tallyText(rubric.reviewer)}`}
          </span>
        )
      }
    >
      <div className="flex flex-col gap-4">
        <p className="text-sm text-muted">
          상황: {section.situation}
          {cardAt !== undefined && ` (카드 발생 ${minutes(cardAt)})`}
        </p>
        {section.event_fired === false ? (
          <p className="rounded-md bg-surface-sunken p-3 text-sm text-muted">
            이벤트 미발생(조기 제출)
          </p>
        ) : section.observed ? (
          <div className="flex flex-col gap-1">
            <p className="text-sm font-medium">관찰된 행동</p>
            <p>{section.observed}</p>
            {memoLines}
          </div>
        ) : (
          <div className="flex flex-col gap-1">
            <p className="rounded-md bg-surface-sunken p-3 text-sm text-muted">
              {section.note ?? "해당 상황에서 관련 행동이 기록되지 않음"}
            </p>
            {memoLines}
          </div>
        )}
        {section.evidence.length > 0 && (
          <div>
            <p className="mb-1 text-sm font-medium">근거</p>
            <ul className="flex flex-col gap-2 text-sm">
              {section.evidence.map((e) => (
                <EvidenceLine key={`${e.type}-${e.id}`} evidence={e} />
              ))}
            </ul>
          </div>
        )}
        {rubric && (
          <div>
            <p className="mb-2 text-sm font-medium">평가표 항목</p>
            <ul className="flex flex-col gap-2">
              {rubric.items.map((item) => (
                <ItemRow
                  key={item.id}
                  item={item}
                  sectionReason={section.no_record_reason}
                  locked={locked}
                  entry={draft[item.id] ?? { choice: "keep", memo: "" }}
                  memoMissing={missing.has(item.id)}
                  onChange={(next) => onChange(item.id, next)}
                />
              ))}
            </ul>
          </div>
        )}
        {((section.aux_facts?.length ?? 0) > 0 ||
          (section.out_of_window_messages?.length ?? 0) > 0) && (
          <div className="rounded-md bg-surface-sunken p-3 text-sm">
            <p className="mb-1 font-medium">점수와 무관한 사실</p>
            <ul className="flex flex-col gap-1 text-muted">
              {section.aux_facts?.map((fact) => (
                <li key={factText(fact)}>{factText(fact)}</li>
              ))}
              {section.out_of_window_messages?.map((m) => (
                <li key={`${m.t_min}-${m.quote}`}>
                  관찰 창 밖 메시지 {minutes(m.t_min)}: “{m.quote}”
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </Card>
  );
}

const AI_GROUPS: { key: NonNullable<AiEvidence["category"]> | "other"; label: string }[] = [
  { key: "delegate", label: "위임" },
  { key: "context", label: "맥락" },
  { key: "verify", label: "검증" },
  { key: "other", label: "기타" },
];

function AiUsage({ usage }: { usage: Report["ai_usage"] }) {
  return (
    <Card title="③ AI 활용" actions={<Badge>판단 기준 없음, 면접 확인용</Badge>}>
      <p className="mb-3">{usage.used ? usage.summary : "사용하지 않음"}</p>
      {AI_GROUPS.map((group) => {
        const rows = usage.evidence.filter((e) => (e.category ?? "other") === group.key);
        if (rows.length === 0) return null;
        return (
          <div key={group.key} className="mb-2">
            <p className="text-sm font-medium">{group.label}</p>
            <ul className="text-sm text-muted">
              {rows.map((e) => (
                <li key={e.call_id}>
                  {minutes(e.t_min)}
                  {e.quote ? ` · “${e.quote}”` : ""}
                  {e.part_no
                    ? ` · ${e.part_no}번 파트에 ${e.reuse === "edited" ? "고쳐서" : e.reuse === "verbatim" ? "그대로" : ""} 반영`
                    : ""}
                </li>
              ))}
            </ul>
          </div>
        );
      })}
    </Card>
  );
}

function History({ report }: { report: Report }) {
  const { history, review } = report.rubric;
  const labels = new Map(report.rubric.elements.flatMap((e) => e.items.map((i) => [i.id, i.text])));
  return (
    <Card title="검토 이력">
      <p className="mb-2 text-sm text-muted">검토 시각 {formatDateTime(report.reviewed_at)}</p>
      {history.length === 0 ? (
        <p className="text-sm text-muted">조정한 항목이 없습니다. 자동 값 그대로 확정되었습니다.</p>
      ) : (
        <ul className="flex flex-col gap-2 text-sm">
          {history.map((row) => (
            <li key={row.item_id}>
              <span className="font-medium">{labels.get(row.item_id) ?? row.item_id}</span>:{" "}
              {valueLabel(row.auto)} → {valueLabel(row.reviewer)}
              <span className="text-muted"> · {row.memo}</span>
            </li>
          ))}
        </ul>
      )}
      {review?.memo && <p className="mt-3 text-sm">전체 메모: {review.memo}</p>}
    </Card>
  );
}

export type ReportViewProps = {
  report: Report;
  /** 검토 제출 요청 중(버튼을 확정 중으로 바꾼다) */
  pending?: boolean;
  /** 서버가 돌려준 오류 문구(already_reviewed, memo_required 등) */
  error?: string | null;
  onReview: (body: { adjustments: Adjustment[]; memo?: string }) => void;
};

export function ReportView({ report, pending, error, onReview }: ReportViewProps) {
  const [draft, setDraft] = useState<Draft>({});
  const [overallMemo, setOverallMemo] = useState("");
  const [missing, setMissing] = useState<Set<string>>(new Set());

  const phase = phaseOf(report);
  const locked = phase !== "draft" || !!pending;
  const adjustments = changedAdjustments(report, draft);
  const reviewer =
    report.rubric.reviewer_total ??
    (adjustments.length > 0 ? previewTotal(report, adjustments) : null);
  const badge = PHASE_BADGE[phase];
  const rubricByElement = new Map(report.rubric.elements.map((e) => [e.element, e]));

  function submit() {
    const blank = missingMemos(adjustments);
    setMissing(new Set(blank));
    if (blank.length === 0) onReview({ adjustments, memo: overallMemo.trim() || undefined });
  }

  return (
    <div className="flex flex-col gap-6">
      <header className="flex flex-col gap-2">
        <div className="flex flex-wrap items-center gap-3">
          <h1 className="text-2xl font-semibold">{report.alias} 리포트</h1>
          <Badge tone={badge.tone}>{badge.label}</Badge>
          <span className="text-sm text-muted">{report.position.name}</span>
        </div>
        <p className="flex flex-wrap items-center gap-x-4 gap-y-1">
          <span>
            기본 점수 <strong>{tallyText(report.rubric.auto_total)}</strong>
          </span>
          {reviewer && (
            <span>
              담당자 점수 <strong>{tallyText(reviewer)}</strong>
              {!report.rubric.reviewer_total && (
                <span className="text-sm text-muted"> (조정 반영 미리보기)</span>
              )}
            </span>
          )}
        </p>
        <p className="text-sm text-muted">{REPORT_NOTICE}</p>
      </header>

      <Deliverable report={report} />

      <section className="flex flex-col gap-4">
        <h2 className="text-lg font-semibold">② 요소별 관찰과 평가표</h2>
        {report.sections.map((section) => (
          <ElementCard
            key={section.element}
            section={section}
            rubric={rubricByElement.get(section.element)}
            locked={locked}
            draft={draft}
            missing={missing}
            onChange={(id, next) => setDraft((prev) => ({ ...prev, [id]: next }))}
          />
        ))}
      </section>

      <AiUsage usage={report.ai_usage} />

      {phase === "final" && <History report={report} />}

      {phase !== "final" && (
        <Card title="검토 완료">
          <div className="flex flex-col gap-3">
            {phase === "draft" && !pending && (
              <Textarea
                label="전체 메모 (선택)"
                value={overallMemo}
                onChange={(e) => setOverallMemo(e.target.value)}
              />
            )}
            {error && (
              <p role="alert" className="text-sm text-danger">
                {error}
              </p>
            )}
            {missing.size > 0 && (
              <p role="alert" className="text-sm text-danger">
                메모가 비어 있는 조정 항목이 있습니다.
              </p>
            )}
            <div>
              <Button onClick={submit} disabled={phase !== "draft"} loading={pending}>
                {phase === "draft" && !pending ? "검토 완료" : "확정 중…"}
              </Button>
            </div>
            <p className="text-sm text-muted">
              검토 완료 뒤에는 입력이 잠기며 값을 다시 바꿀 수 없습니다.
            </p>
          </div>
        </Card>
      )}
    </div>
  );
}
