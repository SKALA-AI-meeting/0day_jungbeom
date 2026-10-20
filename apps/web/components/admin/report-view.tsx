"use client";

// 관리자 리포트: 머리(단계·검토자·삭제 예정일·인쇄) → 요약표 → ① 산출물 → ② 요소 섹션(접힌 카드 소섹션) → ③ AI 활용
// → 메모 → 검토 완료. 채용 관계자가 바로 읽을 문장으로 쓰고 코드 값은 화면에 내지 않는다(docs/frontend/design.md).
import Link from "next/link";
import { useEffect, useState, type ReactNode } from "react";

import {
  Button,
  Chip,
  cn,
  ConfirmDialog,
  Input,
  partTone,
  Textarea,
  type ChipTone,
} from "@/components/ui";

import {
  countsText,
  formatDateTime,
  minText,
  NO_RECORD_TEXT,
  purgeText,
  sessionClock,
} from "./format";
import {
  allItems,
  changedAdjustments,
  countOf,
  finalValue,
  missingMemos,
  phaseOf,
  previewTotal,
  type Choice,
  type Edits,
} from "./review";
import type {
  Adjustment,
  Evidence,
  RecordRef,
  Report,
  ReportCard,
  ReportDocument,
  RubricItem,
} from "./types";

export const REPORT_NOTICE_LINES = [
  "기본 점수: 관찰 기록을 평가표 규칙에 대입해 자동 계산 · 담당자 점수: 검토자가 근거를 보고 조정",
  "합격·불합격 판정 없음 · 활동이 없어 판정하지 않은 항목은 점수에서 제외",
];
export const HONESTY_NOTE = "미완료는 보드 기준이며 지원자가 보드를 갱신하지 않았을 수 있습니다.";
export const AI_HEADER = "판단 기준 없음, 면접 확인용";

const EVIDENCE_LABEL: Record<Evidence["type"], string> = {
  message: "메시지",
  document: "문서 저장",
  share: "보낸 버전",
  open: "받은 문서 열람",
  task_event: "보드 변경",
  doc_view: "자료 열람",
  assistant_call: "어시스턴트",
};

const CHANNEL_LABEL: Record<string, string> = {
  team: "팀 채널",
  dm: "동료 DM",
  manager_dm: "팀장 DM",
  notice: "알림",
};

const STAGE_LABEL = { draft: "검토 대기", approving: "확정 중", final: "검토 완료" } as const;

export function valueLabel(v: 1 | 0 | null): { text: string; tone: ChipTone } {
  if (v === 1) return { text: "충족", tone: "success" };
  if (v === 0) return { text: "미충족", tone: "neutral" };
  return { text: "기록 없음", tone: "outline" };
}

export const basisLabel = (basis: RubricItem["basis"]) =>
  basis === "metric" ? "기록 기반" : "AI 분류 기반";

export type ReportViewProps = {
  report: Report;
  /** 근거의 record_ref → 전체 기록 화면 주소. cardId는 돌아올 때 펼쳐 둘 카드 */
  recordHref: (ref: RecordRef, cardId?: string) => string;
  /** 샘플: 읽기 전용, 검토·메모 없음 */
  sample?: boolean;
  /** 인쇄 미리보기: 접힌 소섹션을 전부 펼친다 */
  printing?: boolean;
  pending?: boolean;
  error?: string | null;
  /** 확정이 오래 끝나지 않음(재시도 안내) */
  stalled?: boolean;
  onReview?: (body: { adjustments: Adjustment[]; memo?: string; reviewer_name: string }) => void;
  onRetry?: () => void;
  onAddNote?: (body: { text: string; reviewer_name: string }) => Promise<void>;
  /** 회사 문서 id → 이름(카탈로그 missions[].documents). 없으면 id를 그대로 보인다 */
  docTitles?: Record<string, string>;
};

function usePrinting(forced?: boolean) {
  const [printing, setPrinting] = useState(false);
  useEffect(() => {
    const on = () => setPrinting(true);
    const off = () => setPrinting(false);
    window.addEventListener("beforeprint", on);
    window.addEventListener("afterprint", off);
    return () => {
      window.removeEventListener("beforeprint", on);
      window.removeEventListener("afterprint", off);
    };
  }, []);
  return forced || printing;
}

function RecordLink({ href }: { href: string | null }) {
  if (!href) return null;
  return (
    <Link
      href={href}
      className="no-print shrink-0 text-xs text-accent underline-offset-4 hover:underline"
    >
      기록에서 보기
    </Link>
  );
}

function Counts3({
  c,
  strong,
}: {
  c: { met: number; unmet: number; no_record: number };
  strong?: boolean;
}) {
  return (
    <span className={cn("tabular-nums whitespace-nowrap", strong && "font-semibold")}>
      {countsText(c)}
    </span>
  );
}

function SectionTitle({ children, sub }: { children: ReactNode; sub?: ReactNode }) {
  return (
    <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1 border-b border-line pb-2">
      <h2 className="text-xl font-semibold">{children}</h2>
      {sub && <span className="text-sm text-muted">{sub}</span>}
    </div>
  );
}

// ── 머리·요약 ──────────────────────────────────────────────

function elementCounts(report: Report, element: string) {
  const el = report.rubric.elements.find((e) => e.element === element);
  if (!el) return null;
  return countOf(el.cards.flatMap((c) => c.items).map(finalValue));
}

function Summary({ report }: { report: Report }) {
  const reviewed = report.rubric.review != null;
  return (
    <table className="w-full border-collapse text-sm">
      <thead>
        <tr className="border-b border-line text-left text-xs text-muted">
          <th className="py-2 pr-3 font-medium">요소</th>
          <th className="py-2 pr-3 font-medium">한 줄 관찰</th>
          <th className="py-2 pr-3 font-medium">기본 점수</th>
          {reviewed && <th className="py-2 font-medium">담당자 점수</th>}
        </tr>
      </thead>
      <tbody>
        {report.summary.map((row) => {
          const adjusted = reviewed ? elementCounts(report, row.element) : null;
          return (
            <tr
              key={row.element}
              className="group border-b border-line align-top hover:bg-surface-sunken/60"
            >
              <td className="py-2.5 pr-3 font-medium whitespace-nowrap">
                <a href={`#el-${row.element}`} className="hover:text-accent">
                  {row.name} <span className="no-print text-subtle group-hover:text-accent">↓</span>
                </a>
              </td>
              <td className={cn("py-2.5 pr-3", !row.line && "text-subtle")}>
                {row.line ?? "관찰 없음"}
              </td>
              <td className="py-2.5 pr-3">
                <Counts3 c={row} />
              </td>
              {reviewed && <td className="py-2.5">{adjusted && <Counts3 c={adjusted} />}</td>}
            </tr>
          );
        })}
        <tr className="align-top">
          <td className="py-2.5 pr-3 font-semibold">합계</td>
          <td className="py-2.5 pr-3 text-muted">요소 {report.summary.length}개</td>
          <td className="py-2.5 pr-3">
            <Counts3 c={report.rubric.auto_total} strong />
          </td>
          {reviewed && (
            <td className="py-2.5">
              {report.rubric.reviewer_total && <Counts3 c={report.rubric.reviewer_total} strong />}
            </td>
          )}
        </tr>
      </tbody>
    </table>
  );
}

// ── ① 산출물 ───────────────────────────────────────────────

function sourceText(s: Report["deliverable"]["final"]["sections"][number]) {
  if (!s.source_doc_id) return s.content.trim() ? "직접 작성" : "비어 있음";
  const who = s.source_owner === "colleague" ? "도현" : "주담당 문서";
  // version null = 보내지 않은 내 문서의 현재 저장본(contracts import)
  const version = s.source_version == null ? " 현재 저장본" : ` v${s.source_version}`;
  return `${who}${version}${s.edited ? " + 편집" : "에서"}`;
}

/** 이보다 긴 섹션은 접고 "더 보기"(인쇄는 전부 펼침) */
const LONG_SECTION_CHARS = 360;

function FinalSections({ report, printing }: { report: Report; printing: boolean }) {
  const [side, setSide] = useState<number | null>(null);
  const [more, setMore] = useState<Record<number, boolean>>({});
  return (
    <ol className="flex flex-col divide-y divide-line rounded-lg border border-line bg-surface">
      {report.deliverable.final.sections.map((s) => {
        const canCompare = s.edited && s.source_content != null;
        const open = canCompare && side === s.part_no && !printing;
        return (
          <li key={s.part_no} className="print-break flex flex-col gap-2 px-5 py-4">
            <div className="flex flex-wrap items-center gap-2">
              <Chip tone={partTone(s.part_no)}>{s.part_no}</Chip>
              <h4 className="font-semibold">{s.title}</h4>
              {canCompare ? (
                <button
                  type="button"
                  aria-expanded={open}
                  onClick={() => setSide(open ? null : s.part_no)}
                  className="press rounded-sm"
                  title="누르면 동료 원문과 나란히 봅니다"
                >
                  <Chip tone="accent">{sourceText(s)} ▾</Chip>
                </button>
              ) : (
                <Chip tone={s.source_doc_id ? "accent" : "neutral"}>{sourceText(s)}</Chip>
              )}
            </div>
            {open ? (
              <div className="grid grid-cols-2 gap-3">
                <div className="rounded-md bg-surface-sunken px-3 py-2">
                  <p className="mb-1 text-xs text-muted">동료 원문 v{s.source_version}</p>
                  <p className="text-sm whitespace-pre-wrap">{s.source_content}</p>
                </div>
                <div className="rounded-md border border-accent/30 px-3 py-2">
                  <p className="mb-1 text-xs text-muted">최종본(주담당 편집)</p>
                  <p className="text-sm whitespace-pre-wrap">{s.content}</p>
                </div>
              </div>
            ) : (
              <>
                <p
                  className={cn(
                    "text-base whitespace-pre-wrap",
                    !s.content.trim() && "text-subtle",
                    s.content.length > LONG_SECTION_CHARS &&
                      !more[s.part_no] &&
                      !printing &&
                      "line-clamp-5",
                  )}
                >
                  {s.content.trim() || "비어 있음"}
                </p>
                {s.content.length > LONG_SECTION_CHARS && !printing && (
                  <button
                    type="button"
                    onClick={() => setMore((m) => ({ ...m, [s.part_no]: !m[s.part_no] }))}
                    className="no-print self-start text-sm text-accent hover:underline"
                  >
                    {more[s.part_no] ? "접기" : "더 보기"}
                  </button>
                )}
              </>
            )}
          </li>
        );
      })}
    </ol>
  );
}

function DocumentsTable({ report }: { report: Report }) {
  return (
    <table className="w-full border-collapse text-sm">
      <thead>
        <tr className="border-b border-line text-left text-xs text-muted">
          <th className="py-2 pr-3 font-medium">파트</th>
          <th className="py-2 pr-3 font-medium">주인</th>
          <th className="py-2 pr-3 font-medium">보낸 버전</th>
          <th className="py-2 font-medium">주담당 열람</th>
        </tr>
      </thead>
      <tbody>
        {report.deliverable.documents
          // 한 번도 쓰거나 보내지 않은 주담당 문서는 같은 파트가 두 번 보이므로 숨긴다
          .filter((d) => !(d.owner === "candidate" && d.empty && d.shares.length === 0))
          .map((d) => (
            <tr key={d.doc_id} className="border-b border-line align-top">
              <td className="py-2 pr-3">
                <span className="flex items-center gap-1.5">
                  <Chip tone={partTone(d.part_no)}>{d.part_no}</Chip>
                  <span className="min-w-0">{d.title}</span>
                </span>
              </td>
              <td className="py-2 pr-3 whitespace-nowrap">
                {d.owner === "colleague" ? "동료" : "주담당"}
              </td>
              <td className="py-2 pr-3">
                {d.shares.length ? (
                  d.shares.map((sh) => (
                    <span key={sh.version} className="mr-2 inline-block whitespace-nowrap">
                      v{sh.version} {CHANNEL_LABEL[sh.channel] ?? sh.channel}{" "}
                      {sessionClock(sh.t_min)}
                    </span>
                  ))
                ) : (
                  <span className="text-subtle">{d.empty ? "빈 문서" : "보내지 않음"}</span>
                )}
              </td>
              <td className="py-2">
                {d.owner === "colleague" ? (
                  d.opened_by_candidate?.length ? (
                    `${d.opened_by_candidate.map((v) => `v${v}`).join("·")} 열람`
                  ) : (
                    <span className="text-subtle">열지 않음</span>
                  )
                ) : (
                  <span className="text-subtle">—</span>
                )}
              </td>
            </tr>
          ))}
      </tbody>
    </table>
  );
}

// ── ② 요소 섹션 ────────────────────────────────────────────

function EvidenceRow({ e, href }: { e: Evidence; href: string | null }) {
  return (
    <li className="flex flex-col gap-1 border-l-2 border-line py-1 pl-3">
      <div className="flex flex-wrap items-center gap-1.5 text-xs text-muted">
        <span className="tabular-nums">{sessionClock(e.t_min)}</span>
        <Chip tone="outline">{EVIDENCE_LABEL[e.type]}</Chip>
        {e.channel && <span>{CHANNEL_LABEL[e.channel] ?? e.channel}</span>}
        {e.flag && <Chip tone="neutral">점수 무관</Chip>}
        <span className="ml-auto">
          <RecordLink href={href} />
        </span>
      </div>
      <p className="text-sm">{e.quote ? `“${e.quote}”` : e.summary}</p>
      {e.context?.prev_persona_message && (
        <p className="text-xs text-subtle">직전: {e.context.prev_persona_message}</p>
      )}
    </li>
  );
}

function ItemRow({
  item,
  editable,
  preview,
  edit,
  window,
  onEdit,
  recordHref,
}: {
  item: RubricItem;
  editable: boolean;
  /** 샘플: 조정 입력을 비활성으로 보여 준다 */
  preview?: boolean;
  edit: { choice: Choice; memo: string } | undefined;
  window?: ReportCard["window"];
  onEdit: (edit: { choice: Choice; memo: string }) => void;
  recordHref: (ref: RecordRef) => string;
}) {
  const auto = valueLabel(item.auto);
  const choice = edit?.choice ?? "auto";
  const next = choice === "1" ? 1 : choice === "0" ? 0 : null;
  const changed = choice !== "auto" && next !== item.auto;
  const firstRef = item.evidence.find((e) => e.record_ref)?.record_ref;
  return (
    <li className="flex flex-col gap-1.5 py-2.5">
      <div className="flex flex-wrap items-center gap-1.5">
        <span className="min-w-0 flex-1 text-sm">{item.text.replace(" (pilot_value)", "")}</span>
        {changed ? (
          <Chip tone="warning">
            {auto.text} → {valueLabel(next).text}(조정)
          </Chip>
        ) : (
          <Chip tone={auto.tone}>{auto.text}</Chip>
        )}
        <Chip tone="outline">{basisLabel(item.basis)}</Chip>
        {firstRef && <RecordLink href={recordHref(firstRef)} />}
      </div>
      {/* AI 분류 항목은 판정 창의 지원자 메시지가 근거다. 없으면 없다는 사실을 창과 함께 보인다 */}
      {item.basis === "label" && item.evidence.length > 0 && (
        <ul className="flex flex-col gap-0.5">
          {item.evidence.map((e) => (
            <li key={`${e.type}-${e.id}`} className="flex gap-2 text-xs text-muted">
              <span className="tabular-nums">{sessionClock(e.t_min)}</span>
              <span className="min-w-0 flex-1 truncate">{e.quote ?? e.summary}</span>
            </li>
          ))}
        </ul>
      )}
      {item.basis === "label" && item.evidence.length === 0 && window && (
        <p className="text-xs text-muted">
          판정 창 {sessionClock(window.start_min)}~{sessionClock(window.end_min)} 지원자 메시지 없음
        </p>
      )}
      <div className="flex flex-wrap gap-x-3 text-xs text-muted">
        {item.auto === null && item.no_record_reason && (
          <span>{NO_RECORD_TEXT[item.no_record_reason]}</span>
        )}
        {item.minutes !== undefined && (
          <span>{item.minutes == null ? "관련 메시지 없음" : `실제 ${minText(item.minutes)}`}</span>
        )}
        {item.adjusted && (
          <span className="text-ink">
            담당자 값 {valueLabel(item.reviewer).text}
            {item.memo && ` · ${item.memo}`}
          </span>
        )}
      </div>
      {(editable || preview) && (
        <div className="no-print flex flex-wrap items-start gap-2">
          <select
            aria-label={`${item.text} 담당자 값`}
            disabled={preview}
            value={choice}
            onChange={(e) => onEdit({ choice: e.target.value as Choice, memo: edit?.memo ?? "" })}
            className="rounded-md border border-line bg-surface px-2 py-1 text-sm"
          >
            <option value="auto">자동 값 유지</option>
            <option value="1">충족</option>
            <option value="0">미충족</option>
            <option value="null">기록 없음</option>
          </select>
          {changed && (
            <input
              aria-label="조정 메모"
              value={edit?.memo ?? ""}
              onChange={(e) => onEdit({ choice, memo: e.target.value })}
              placeholder="바꾼 이유(필수)"
              className={cn(
                "min-w-0 flex-1 rounded-md border px-2 py-1 text-sm",
                edit?.memo.trim() ? "border-line" : "border-danger/60",
              )}
            />
          )}
        </div>
      )}
    </li>
  );
}

/** 작성자는 데이터의 owner로만 정한다(문서 id 모양으로 추측하지 않는다. 실제 id는 UUID) */
function HonestyFacts({ card, documents }: { card: ReportCard; documents: ReportDocument[] }) {
  const f = card.facts!;
  const owners = new Map<string, "candidate" | "colleague">([
    ...documents.map((d) => [d.doc_id, d.owner] as const),
    ...f.shares.map((sh) => [sh.doc_id, sh.owner] as const),
  ]);
  const ownerWord = (docId: string) => {
    const owner = owners.get(docId);
    return owner === "colleague" ? "동료" : owner === "candidate" ? "주담당" : "출처 미상";
  };
  return (
    <div className="flex flex-col gap-2">
      <p className="text-xs font-medium text-muted">사실 입력</p>
      <table className="w-full border-collapse text-sm">
        <tbody>
          <tr className="border-b border-line align-top">
            <th className="w-32 py-1.5 pr-3 text-left font-normal text-muted">공유 이력</th>
            <td className="py-1.5">
              {f.shares
                .map(
                  (s) =>
                    `${s.part_no}번(${s.owner === "colleague" ? "동료" : "주담당"}) ${s.versions.map((v) => `v${v.version} ${sessionClock(v.t_min)}`).join(", ")}`,
                )
                .join(" / ")}
            </td>
          </tr>
          <tr className="border-b border-line align-top">
            <th className="py-1.5 pr-3 text-left font-normal text-muted">최종본 출처</th>
            <td className="py-1.5">
              {f.final_sections
                .map(
                  (s) =>
                    `${s.part_no}번 ${s.source_doc_id ? `${ownerWord(s.source_doc_id)} ${s.source_version == null ? "현재 저장본" : `v${s.source_version}`}${s.edited ? "+편집" : ""}` : "직접 작성"}`,
                )
                .join(" / ")}
            </td>
          </tr>
          <tr className="border-b border-line align-top">
            <th className="py-1.5 pr-3 text-left font-normal text-muted">미완료 파트</th>
            <td className="py-1.5">
              {f.tasks_not_done.length ? `${f.tasks_not_done.join("·")}번(보드 완료 아님)` : "없음"}
              {f.empty_sections.length > 0 && ` · 빈 섹션 ${f.empty_sections.join("·")}번`}
            </td>
          </tr>
          <tr className="align-top">
            <th className="py-1.5 pr-3 text-left font-normal text-muted">방향 변경 뒤 버전</th>
            <td className="py-1.5">
              {f.changed_after_adaptability == null
                ? "해당 없음"
                : f.changed_after_adaptability
                  ? "있음"
                  : "없음"}
            </td>
          </tr>
        </tbody>
      </table>
      <p className="text-xs text-muted">※ {HONESTY_NOTE}</p>
    </div>
  );
}

function CardSection({
  card,
  items,
  open,
  onToggle,
  editable,
  preview,
  gaps,
  documents,
  edits,
  onEdit,
  recordHref,
}: {
  card: ReportCard;
  items: RubricItem[];
  open: boolean;
  onToggle: (open: boolean) => void;
  editable: boolean;
  preview?: boolean;
  gaps: Report["connection_gaps"];
  documents: ReportDocument[];
  edits: Edits;
  onEdit: (id: string, edit: { choice: Choice; memo: string }) => void;
  recordHref: (ref: RecordRef, cardId?: string) => string;
}) {
  const memos = items.filter((i) => i.adjusted && i.memo);
  const link = (ref: RecordRef) => recordHref(ref, card.card_id);
  // 관찰 창과 겹친 연결 끊김은 "활동 없음"을 지원자 탓으로 읽지 않게 카드 머리에 보인다
  const overlap = card.window
    ? gaps.filter((g) => g.from_t_min < card.window!.end_min && g.to_t_min > card.window!.start_min)
    : [];
  return (
    <details
      id={`card-${card.card_id}`}
      open={open}
      onToggle={(e) => onToggle((e.currentTarget as HTMLDetailsElement).open)}
      className="print-break scroll-mt-6 rounded-lg border border-line bg-surface"
    >
      <summary className="flex cursor-pointer list-none flex-wrap items-center gap-2 px-4 py-3 select-none">
        <span
          aria-hidden
          className={cn("text-subtle transition-transform duration-150", open && "rotate-90")}
        >
          ▸
        </span>
        <span className="font-medium">{card.name}</span>
        <span className="text-xs text-muted">
          {card.event_fired && card.card_at_t_min != null
            ? sessionClock(card.card_at_t_min)
            : "이벤트 미발생(조기 제출)"}
        </span>
        {overlap.map((g) => (
          <Chip key={g.from_t_min} tone="danger">
            이 구간 연결 끊김 {sessionClock(g.from_t_min)}~{sessionClock(g.to_t_min)}
          </Chip>
        ))}
        <span className="ml-auto flex flex-wrap gap-1">
          {items.map((i) => {
            const v = valueLabel(finalValue(i));
            return (
              <Chip key={i.id} tone={v.tone} title={i.text}>
                {v.text}
              </Chip>
            );
          })}
        </span>
      </summary>
      <div className="flex flex-col gap-4 border-t border-line px-4 py-4">
        <dl className="grid grid-cols-[88px_1fr] gap-x-3 gap-y-1.5 text-sm">
          <dt className="text-muted">상황</dt>
          <dd>{card.situation}</dd>
          <dt className="text-muted">카드 발생</dt>
          <dd>
            {card.event_fired && card.card_at_t_min != null
              ? sessionClock(card.card_at_t_min)
              : "이벤트 미발생(조기 제출)"}
          </dd>
          {card.window && (
            <>
              <dt className="text-muted">판정 창</dt>
              <dd>
                {sessionClock(card.window.start_min)}~{sessionClock(card.window.end_min)}
              </dd>
            </>
          )}
          <dt className="text-muted">관찰된 행동</dt>
          <dd>
            {card.observed ? (
              card.observed
            ) : (
              <span className="text-subtle">
                {card.note ??
                  (card.no_record_reason ? NO_RECORD_TEXT[card.no_record_reason] : "관찰 없음")}
              </span>
            )}
            {memos.map((i) => (
              <span key={i.id} className="mt-1 block rounded-sm bg-warning-soft px-2 py-1 text-xs">
                담당자 메모: {i.memo}
              </span>
            ))}
          </dd>
        </dl>
        {card.evidence.length > 0 && (
          <div className="flex flex-col gap-1.5">
            <p className="text-xs font-medium text-muted">근거</p>
            <ul className="flex flex-col gap-2">
              {card.evidence.map((e) => (
                <EvidenceRow
                  key={`${e.type}-${e.id}`}
                  e={e}
                  href={e.record_ref ? link(e.record_ref) : null}
                />
              ))}
            </ul>
          </div>
        )}
        {card.facts && <HonestyFacts card={card} documents={documents} />}
        <div>
          <p className="text-xs font-medium text-muted">평가표 항목</p>
          {preview && (
            <p className="text-xs text-muted">실제 리포트: 항목 값 변경·메모 입력(샘플은 비활성)</p>
          )}
          <ul className="divide-y divide-line">
            {items.map((item) => (
              <ItemRow
                key={item.id}
                item={item}
                editable={editable}
                preview={preview}
                window={card.window}
                edit={edits[item.id]}
                onEdit={(edit) => onEdit(item.id, edit)}
                recordHref={link}
              />
            ))}
          </ul>
        </div>
      </div>
    </details>
  );
}

// ── ③ AI 활용·메모·검토 ────────────────────────────────────

function AiUsage({
  report,
  recordHref,
  docTitles,
}: {
  report: Report;
  recordHref: (ref: RecordRef) => string;
  docTitles?: Record<string, string>;
}) {
  const { ai_usage } = report;
  if (!ai_usage.used) return <p className="text-muted">사용하지 않음</p>;
  return (
    <ol className="flex flex-col gap-3">
      {ai_usage.events.map((e) => (
        <li
          key={e.call_id}
          className="print-break flex flex-col gap-1.5 rounded-lg border border-line bg-surface px-4 py-3"
        >
          <div className="flex flex-wrap items-center gap-2 text-xs text-muted">
            <span className="tabular-nums">{sessionClock(e.t_min)}</span>
            {e.cited_doc_ids.map((d) => (
              <Chip key={d} tone="outline">
                {docTitles?.[d] ?? d}
              </Chip>
            ))}
            <span>
              {e.applied_part == null
                ? "반영된 파트 없음"
                : `반영된 파트: ${e.applied_part === "final" ? "최종본" : `${e.applied_part}번`}`}
            </span>
            <span className="ml-auto">
              <RecordLink
                href={recordHref({ type: "assistant_call", id: e.call_id, t_min: e.t_min })}
              />
            </span>
          </div>
          <p className="text-sm">
            <span className="text-muted">요청 </span>“{e.request_quote}”
          </p>
          <p className="text-sm">
            <span className="text-muted">응답 </span>
            {e.response_quote}
          </p>
        </li>
      ))}
    </ol>
  );
}

function Notes({
  report,
  onAddNote,
}: {
  report: Report;
  onAddNote?: ReportViewProps["onAddNote"];
}) {
  const [text, setText] = useState("");
  const [name, setName] = useState(report.rubric.review?.reviewer_name ?? "");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  return (
    <div className="flex flex-col gap-3">
      {report.notes.length === 0 ? (
        <p className="text-sm text-muted">리포트 메모 없음</p>
      ) : (
        <ul className="flex flex-col gap-2">
          {report.notes.map((n) => (
            <li key={n.id} className="rounded-md border border-line bg-surface px-3 py-2 text-sm">
              <p>{n.text}</p>
              <p className="text-xs text-subtle">
                {n.reviewer_name} · {formatDateTime(n.created_at)}
              </p>
            </li>
          ))}
        </ul>
      )}
      {onAddNote && (
        <form
          className="no-print flex flex-col gap-2"
          onSubmit={async (event) => {
            event.preventDefault();
            setPending(true);
            setError(null);
            try {
              await onAddNote({ text, reviewer_name: name });
              setText("");
            } catch {
              setError("메모를 저장하지 못했어요.");
            } finally {
              setPending(false);
            }
          }}
        >
          <Textarea
            label="리포트 메모 추가"
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder="면접 확인 사항 등 · 점수는 그대로"
          />
          <div className="flex items-end gap-2">
            <Input label="작성자" value={name} onChange={(e) => setName(e.target.value)} />
            <Button
              type="submit"
              variant="secondary"
              loading={pending}
              disabled={!text.trim() || !name.trim()}
            >
              메모 추가
            </Button>
          </div>
          {error && <p className="text-sm text-danger">{error}</p>}
        </form>
      )}
    </div>
  );
}

function ReviewFooter({
  report,
  edits,
  pending,
  error,
  onReview,
}: {
  report: Report;
  edits: Edits;
  pending?: boolean;
  error?: string | null;
  onReview: NonNullable<ReportViewProps["onReview"]>;
}) {
  const [memo, setMemo] = useState("");
  const [name, setName] = useState("");
  const [confirm, setConfirm] = useState(false);
  const adjustments = changedAdjustments(report, edits);
  const missing = missingMemos(adjustments);
  const total = previewTotal(report, adjustments);
  const ready = name.trim() && missing.length === 0;
  return (
    <section className="no-print flex flex-col gap-3 rounded-lg border border-line bg-surface p-5">
      <h2 className="text-lg font-semibold">검토 완료</h2>
      <p className="text-sm text-muted">
        조정 {adjustments.length}건 · 담당자 점수 미리보기 <Counts3 c={total} />
      </p>
      <Textarea label="전체 메모(선택)" value={memo} onChange={(e) => setMemo(e.target.value)} />
      <Input label="검토자 이름" value={name} onChange={(e) => setName(e.target.value)} required />
      {missing.length > 0 && (
        <p className="text-sm text-danger">메모 필요: 값을 바꾼 항목 {missing.length}건</p>
      )}
      {error && (
        <p role="alert" className="text-sm text-danger">
          {error}
        </p>
      )}
      <div>
        <Button disabled={!ready} loading={pending} onClick={() => setConfirm(true)}>
          검토 완료
        </Button>
      </div>
      <ConfirmDialog
        open={confirm}
        onOpenChange={setConfirm}
        title="검토를 완료할까요?"
        description="검토 완료 후 점수 변경 불가. 리포트 메모는 계속 추가 가능."
        confirmLabel="검토 완료"
        pending={pending}
        onConfirm={() => {
          setConfirm(false);
          onReview({ adjustments, memo: memo.trim() || undefined, reviewer_name: name.trim() });
        }}
      />
    </section>
  );
}

export function ReportView(props: ReportViewProps) {
  const { report, recordHref, sample } = props;
  const printing = usePrinting(props.printing);
  const phase = phaseOf(report);
  const editable = !sample && phase === "draft" && !!props.onReview;
  const [opened, setOpened] = useState<Record<string, boolean>>({});
  // 전체 기록에서 돌아오면(#card-…) 그 카드를 펼치고 그 자리로 간다
  useEffect(() => {
    const id = window.location.hash.match(/^#card-(.+)$/)?.[1];
    if (!id) return;
    const frame = requestAnimationFrame(() => {
      setOpened((o) => ({ ...o, [id]: true }));
      document.getElementById(`card-${id}`)?.scrollIntoView();
    });
    return () => cancelAnimationFrame(frame);
  }, []);
  const [edits, setEdits] = useState<Edits>({});
  const items = new Map(allItems(report).map((i) => [i.id, i]));
  const cardItems = (cardId: string) =>
    report.rubric.elements
      .flatMap((e) => e.cards)
      .find((c) => c.card_id === cardId)
      ?.items.map((i) => items.get(i.id)!) ?? [];
  const purge = purgeText(report.purge_at);
  const review = report.rubric.review;

  return (
    <article className="flex flex-col gap-8">
      <header className="flex flex-col gap-3">
        {sample && (
          <p className="no-print rounded-md bg-accent-soft px-3 py-2 text-sm text-accent-strong">
            샘플 리포트 · 예시 지원자 기록으로 만든 화면
          </p>
        )}
        <div className="flex flex-wrap items-center gap-3">
          <h1 className="text-2xl font-semibold">{report.alias}</h1>
          <Chip tone={phase === "final" ? "success" : phase === "approving" ? "warning" : "accent"}>
            {STAGE_LABEL[phase]}
          </Chip>
          <span className="text-sm text-muted">{report.position.name}</span>
          <Button
            variant="secondary"
            size="sm"
            className="no-print ml-auto"
            onClick={() => window.print()}
          >
            인쇄
          </Button>
        </div>
        <p className="flex flex-wrap gap-x-4 text-sm text-muted">
          <span>생성 {formatDateTime(report.generated_at)}</span>
          {review && (
            <span>
              검토자 {review.reviewer_name}
              {report.reviewed_at && ` · ${formatDateTime(report.reviewed_at)}`}
            </span>
          )}
          {purge && !sample && <span>{purge}</span>}
          {report.connection_gaps.length > 0 && (
            <span>
              연결 끊김{" "}
              {report.connection_gaps
                .map((g) => `${sessionClock(g.from_t_min)}~${sessionClock(g.to_t_min)}`)
                .join(", ")}{" "}
              (점수 무관)
            </span>
          )}
        </p>
        <div className="flex flex-col gap-0.5 rounded-md bg-surface-sunken px-4 py-3 text-sm">
          {REPORT_NOTICE_LINES.map((line) => (
            <p key={line}>{line}</p>
          ))}
          {!sample && phase === "draft" && (
            <p className="text-muted">
              조정: 카드 펼침 → 항목 값 변경(메모 필수) → 맨 아래 검토 완료
            </p>
          )}
        </div>
        {review?.memo && <p className="text-sm">검토 메모: {review.memo}</p>}
        <Summary report={report} />
      </header>

      <section className="flex flex-col gap-4">
        <SectionTitle
          sub={`분업 결정: ${report.deliverable.division_decided_by === "colleague_default" ? "동료 기본안" : "주담당"}`}
        >
          ① 산출물
        </SectionTitle>
        <h3 className="text-sm font-semibold text-muted">최종본</h3>
        <FinalSections report={report} printing={printing} />
        <h3 className="text-sm font-semibold text-muted">주고받은 문서</h3>
        <DocumentsTable report={report} />
        {report.deliverable.final_report_message && (
          <>
            <h3 className="text-sm font-semibold text-muted">최종 보고</h3>
            <blockquote className="flex flex-col gap-1 rounded-lg border border-line bg-surface px-4 py-3">
              <p className="text-base">“{report.deliverable.final_report_message.content}”</p>
              <span className="flex items-center gap-2 text-xs text-muted">
                {sessionClock(report.deliverable.final_report_message.t_min)}
                <RecordLink
                  href={recordHref({
                    type: "message",
                    id: report.deliverable.final_report_message.id,
                    t_min: report.deliverable.final_report_message.t_min,
                  })}
                />
              </span>
            </blockquote>
          </>
        )}
      </section>

      <section className="flex flex-col gap-6">
        <SectionTitle sub="카드를 누르면 근거·항목 펼침">② 요소별 관찰</SectionTitle>
        {report.sections.map((section) => {
          const summary = report.summary.find((s) => s.element === section.element);
          return (
            <div
              key={section.element}
              id={`el-${section.element}`}
              className="flex scroll-mt-6 flex-col gap-2"
            >
              <div className="flex flex-wrap items-baseline gap-x-3">
                <h3 className="text-lg font-semibold">{section.name}</h3>
                {summary && <Counts3 c={summary} />}
              </div>
              {summary && (
                <p className={cn("text-sm", !summary.line && "text-subtle")}>
                  {summary.line ?? "관찰 없음"}
                </p>
              )}
              <div className="flex flex-col gap-2">
                {section.cards.map((card) => (
                  <CardSection
                    key={card.card_id}
                    card={card}
                    items={cardItems(card.card_id)}
                    open={printing || !!opened[card.card_id]}
                    onToggle={(open) =>
                      !printing && setOpened((o) => ({ ...o, [card.card_id]: open }))
                    }
                    editable={editable}
                    preview={sample}
                    gaps={report.connection_gaps}
                    documents={report.deliverable.documents}
                    edits={edits}
                    onEdit={(id, edit) => setEdits((e) => ({ ...e, [id]: edit }))}
                    recordHref={recordHref}
                  />
                ))}
              </div>
            </div>
          );
        })}
      </section>

      <section className="flex flex-col gap-4">
        <SectionTitle sub={AI_HEADER}>③ AI 활용</SectionTitle>
        <AiUsage report={report} recordHref={recordHref} docTitles={props.docTitles} />
      </section>

      {!sample && phase !== "draft" && (
        <section className="flex flex-col gap-4">
          <SectionTitle sub="검토 완료 뒤 덧붙이는 리포트 전체 메모 · 점수는 그대로">
            리포트 메모
          </SectionTitle>
          <Notes report={report} onAddNote={props.onAddNote} />
        </section>
      )}

      {editable && props.onReview && (
        <ReviewFooter
          report={report}
          edits={edits}
          pending={props.pending}
          error={props.error}
          onReview={props.onReview}
        />
      )}
      {!sample && phase === "approving" && (
        <section
          role="status"
          className="no-print flex flex-col gap-2 rounded-lg border border-warning/30 bg-warning-soft px-5 py-4"
        >
          {props.stalled ? (
            <>
              <p className="text-sm">조정은 저장되어 있습니다. 확정만 다시 시도합니다.</p>
              <div>
                <Button
                  size="sm"
                  variant="secondary"
                  loading={props.pending}
                  onClick={props.onRetry}
                >
                  확정 다시 시도
                </Button>
              </div>
            </>
          ) : (
            <p className="text-sm">확정 중… 곧 검토 완료로 전환</p>
          )}
          {/* 재시도 요청 자체가 실패한 경우도 이 안내 안에 보인다 */}
          {props.error && (
            <p role="alert" className="text-sm text-danger">
              {props.error}
            </p>
          )}
        </section>
      )}
    </article>
  );
}
