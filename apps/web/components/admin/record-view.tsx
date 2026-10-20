"use client";

// 전체 기록(읽기 전용 타임라인). 리포트의 "기록에서 보기"로 들어오면 #<type>-<id> 줄로 스크롤하고 하이라이트한다.
import Link from "next/link";
import { useEffect, useState, useSyncExternalStore } from "react";

import { Button, Chip, cn } from "@/components/ui";

import { sessionClock } from "./format";
import { recordAnchor } from "./review";
import type { RecordEntry } from "./types";

type Kind = "talk" | "doc" | "board" | "assistant" | "gap";

const KIND_OF: Record<RecordEntry["type"], Kind> = {
  message: "talk",
  notice: "talk",
  share: "doc",
  open: "doc",
  task_event: "board",
  assistant_call: "assistant",
  connection_gap: "gap",
};

const KIND_LABEL: Record<Kind, string> = {
  talk: "대화",
  doc: "문서",
  board: "보드",
  assistant: "어시스턴트",
  gap: "접속 끊김",
};

const TYPE_LABEL: Record<RecordEntry["type"], string> = {
  message: "메시지",
  notice: "알림",
  share: "보냄",
  open: "열람",
  task_event: "보드",
  assistant_call: "어시스턴트",
  connection_gap: "끊김",
};

const CHANNEL_LABEL: Record<string, string> = {
  team: "팀 채널",
  dm: "동료 DM",
  manager_dm: "팀장 DM",
  notice: "알림",
};
const BY_LABEL: Record<string, string> = {
  candidate: "지원자",
  colleague: "동료",
  manager: "팀장",
  system: "시스템",
};

const FIELD_LABEL: Record<string, string> = {
  assignee: "담당",
  due_min: "언제까지",
  status: "상태",
  order: "순서",
};

/**
 * 서버 요약의 코드 값을 사람 말로: "1번 카드 assignee 변경(12분)" → "1번 담당 변경 · 00:12".
 * 바뀐 값(누구로·언제까지)은 기록 응답에 없어 보이지 못한다(보고서 변경 요청).
 */
export function readable(e: RecordEntry) {
  const m = /^(\d+)번 카드 (\w+) 변경\(([\d.]+)분\)$/.exec(e.summary);
  if (m) return `${m[1]}번 ${FIELD_LABEL[m[2]] ?? m[2]} 변경 · ${sessionClock(Number(m[3]))}`;
  return e.summary.replace(/\(([\d.]+)분\)$/, (_, t: string) => ` · ${sessionClock(Number(t))}`);
}

export type RecordFilter = { kind: Kind | "all"; channel: string | "all"; by: string | "all" };

export function filterRecord(entries: RecordEntry[], f: RecordFilter) {
  return entries.filter(
    (e) =>
      (f.kind === "all" || KIND_OF[e.type] === f.kind) &&
      (f.channel === "all" || e.channel === f.channel) &&
      (f.by === "all" || e.by === f.by),
  );
}

function Select({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: string;
  options: [string, string][];
  onChange: (v: string) => void;
}) {
  return (
    <label className="flex items-center gap-1.5 text-sm text-muted">
      {label}
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="rounded-md border border-line bg-surface px-2 py-1 text-sm text-ink"
      >
        {options.map(([v, l]) => (
          <option key={v} value={v}>
            {l}
          </option>
        ))}
      </select>
    </label>
  );
}

export function RecordView({
  entries,
  backHref,
  highlight: forced,
}: {
  entries: RecordEntry[];
  backHref: string;
  /** 테스트·서버 렌더용. 없으면 주소의 #앵커를 읽는다 */
  highlight?: string;
}) {
  const [hash, setHash] = useState<string | null>(forced ?? null);
  const [filter, setFilter] = useState<RecordFilter>({ kind: "all", channel: "all", by: "all" });
  const highlight = forced ?? hash;

  useEffect(() => {
    const read = () => setHash(window.location.hash.slice(1) || null);
    read();
    window.addEventListener("hashchange", read);
    return () => window.removeEventListener("hashchange", read);
  }, []);
  useEffect(() => {
    if (highlight) document.getElementById(highlight)?.scrollIntoView({ block: "center" });
  }, [highlight, entries.length]);

  const rows = filterRecord(entries, filter);
  // 리포트 카드에서 왔으면 돌아갈 때 그 카드를 펼친다
  const card = useSyncExternalStore(
    () => () => {},
    () => new URLSearchParams(window.location.search).get("card"),
    () => null,
  );
  const back = card ? `${backHref}#card-${card}` : backHref;
  return (
    <div className="flex flex-col gap-4">
      {/* 머리 고정: 길게 내려가도 "리포트로 돌아가기"와 필터가 남는다 */}
      <div className="no-print sticky top-0 z-10 -mx-1 flex flex-wrap items-center gap-3 border-b border-line bg-canvas/95 px-1 py-2 backdrop-blur-[2px]">
        <Link href={back}>
          <Button variant="secondary" size="sm">
            ← 리포트로 돌아가기
          </Button>
        </Link>
        <Select
          label="종류"
          value={filter.kind}
          onChange={(v) => setFilter((f) => ({ ...f, kind: v as RecordFilter["kind"] }))}
          options={[["all", "전체"], ...(Object.entries(KIND_LABEL) as [string, string][])]}
        />
        <Select
          label="채널"
          value={filter.channel}
          onChange={(v) => setFilter((f) => ({ ...f, channel: v }))}
          options={[["all", "전체"], ...Object.entries(CHANNEL_LABEL)]}
        />
        <Select
          label="주체"
          value={filter.by}
          onChange={(v) => setFilter((f) => ({ ...f, by: v }))}
          options={[["all", "전체"], ...Object.entries(BY_LABEL)]}
        />
        <Button variant="ghost" size="sm" className="ml-auto" onClick={() => window.print()}>
          인쇄
        </Button>
      </div>
      <p className="text-sm text-muted">세션 전체 시간순 기록 · 읽기 전용</p>
      {rows.length === 0 ? (
        <p className="py-10 text-center text-sm text-muted">조건에 맞는 기록 없음</p>
      ) : (
        <ol className="flex flex-col rounded-lg border border-line bg-surface">
          {rows.map((e) => {
            const anchor = recordAnchor(e.ref);
            const on = anchor === highlight;
            return (
              <li
                key={anchor}
                id={anchor}
                aria-current={on || undefined}
                className={cn(
                  "grid scroll-mt-20 grid-cols-[56px_88px_1fr] gap-3 border-b border-line px-4 py-2.5 text-sm transition-colors duration-300 last:border-b-0",
                  on && "bg-accent-soft",
                )}
              >
                <span className="text-muted tabular-nums">{sessionClock(e.t_min)}</span>
                <span className="flex flex-col items-start gap-1">
                  <Chip tone={e.type === "connection_gap" ? "danger" : "outline"}>
                    {TYPE_LABEL[e.type]}
                  </Chip>
                </span>
                <span className="min-w-0">
                  <span className="text-xs text-muted">
                    {e.type === "notice" ? "리서치 담당" : (BY_LABEL[e.by] ?? e.by)}
                    {e.channel && ` · ${CHANNEL_LABEL[e.channel] ?? e.channel}`}
                  </span>
                  <span className="block break-words">{readable(e)}</span>
                </span>
              </li>
            );
          })}
        </ol>
      )}
    </div>
  );
}
