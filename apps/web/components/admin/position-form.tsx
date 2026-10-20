"use client";

import { useState, type FormEvent } from "react";

import { Badge, Button, Card, Input } from "@/components/ui";

import type { Catalog } from "./types";

export const MAX_ELEMENTS = 4;

/** 요소는 1~4개. 위반이면 안내 문구, 통과하면 null. 서버도 같은 규칙을 invalid_elements(400)로 검증한다. */
export function validateElements(selected: string[]): string | null {
  if (selected.length < 1) return "평가 요소를 1개 이상 골라 주세요.";
  if (selected.length > MAX_ELEMENTS)
    return `평가 요소는 최대 ${MAX_ELEMENTS}개까지 고를 수 있습니다.`;
  return null;
}

const FLOW_NAMES: Record<string, string> = {
  kickoff: "킥오프",
  division: "분업 논의",
  review: "상호 리뷰",
  report_request: "마감 보고 요청",
};

export type TimelineRow = { label: string; at: number };

/**
 * 선택한 요소에 따른 카드 시각(분). 요소 카드가 n개면 n=1일 때 1/4 지점, n≥2면 i번째가 1/4 + i×(1/2)/n 지점이고
 * 흐름 카드는 카탈로그의 at_fraction이다(배치 규칙은 catalog.timeline.element_fraction_rule).
 */
export function timelineRows(catalog: Catalog, selected: string[]): TimelineRow[] {
  const minutes = catalog.session_minutes;
  const picked = catalog.elements.filter((e) => selected.includes(e.id));
  const n = picked.length;
  const rows: TimelineRow[] = catalog.timeline.flow.map((card) => ({
    label: FLOW_NAMES[card.card_id] ?? card.card_id,
    at: card.at_fraction * minutes,
  }));
  picked.forEach((element, i) => {
    const fraction = n === 1 ? 0.25 : 0.25 + (i * 0.5) / n;
    rows.push({ label: `${element.name} 상황`, at: fraction * minutes });
  });
  return rows.sort((a, b) => a.at - b.at);
}

export type PositionFormProps = {
  catalog: Catalog;
  pending?: boolean;
  /** 서버가 돌려준 오류 문구 */
  error?: string | null;
  onSubmit: (value: { name: string; elements: string[] }) => void;
};

export function PositionForm({ catalog, pending, error, onSubmit }: PositionFormProps) {
  const [name, setName] = useState("");
  const [selected, setSelected] = useState<string[]>([]);
  const [problem, setProblem] = useState<string | null>(null);

  const toggle = (id: string) =>
    setSelected((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]));

  function submit(event: FormEvent) {
    event.preventDefault();
    const invalid = validateElements(selected);
    setProblem(invalid);
    if (!invalid) onSubmit({ name: name.trim(), elements: selected });
  }

  const shown = problem ?? error;
  return (
    <form className="flex flex-col gap-6" onSubmit={submit}>
      <Input label="채용 건 이름" value={name} onChange={(e) => setName(e.target.value)} required />
      <fieldset className="flex flex-col gap-3">
        <legend className="mb-1 text-sm font-medium">
          평가 요소{" "}
          <span className="text-muted">
            ({selected.length}/{MAX_ELEMENTS}개 선택)
          </span>
        </legend>
        {catalog.elements.map((element) => (
          <label key={element.id} className="cursor-pointer">
            <Card className={selected.includes(element.id) ? "border-accent" : undefined}>
              <div className="flex items-start gap-3">
                <input
                  type="checkbox"
                  className="mt-1.5"
                  checked={selected.includes(element.id)}
                  onChange={() => toggle(element.id)}
                />
                <div className="flex flex-col gap-2">
                  <p className="font-medium">{element.name}</p>
                  <p className="text-sm text-muted">{element.situation_public}</p>
                  <ul className="flex flex-col gap-1 text-sm">
                    {element.rubric.map((item) => (
                      <li key={item.id} className="flex items-center gap-2">
                        <span className="text-subtle">·</span>
                        <span>{item.text}</span>
                        {item.pilot_value && (
                          <span title="시험 운영 기준">
                            <Badge tone="warning">시험 운영 기준</Badge>
                          </span>
                        )}
                      </li>
                    ))}
                  </ul>
                </div>
              </div>
            </Card>
          </label>
        ))}
      </fieldset>
      <Card title="타임라인 미리보기">
        {selected.length === 0 ? (
          <p className="text-sm text-muted">요소를 고르면 카드가 나오는 시각이 표시됩니다.</p>
        ) : (
          <ul className="flex flex-col gap-1 text-sm">
            {timelineRows(catalog, selected).map((row) => (
              <li key={row.label}>
                <span className="inline-block w-16 text-subtle">{Math.round(row.at)}분</span>
                {row.label}
              </li>
            ))}
          </ul>
        )}
        <p className="mt-2 text-sm text-muted">
          세션 {catalog.session_minutes}분 기준, 시각만 표시합니다.{" "}
          {catalog.timeline.element_fraction_rule}
        </p>
      </Card>
      <Card title="지원자 안내 문안">
        <p className="mb-2 text-sm text-muted">
          초대를 만들면 아래 문안의 자리표시자가 채워집니다. 이메일은 발송되지 않습니다.
        </p>
        <pre className="whitespace-pre-wrap rounded-md bg-surface-sunken p-3 text-sm">
          {catalog.candidate_notice_template}
        </pre>
      </Card>
      <p className="text-sm text-muted">
        평가표 항목은 지원자에게 세션 전에 공개되지 않고, 종료 뒤 디브리핑에서 공개됩니다.
      </p>
      {shown && (
        <p role="alert" className="text-sm text-danger">
          {shown}
        </p>
      )}
      <div>
        <Button type="submit" loading={pending}>
          채용 건 만들기
        </Button>
      </div>
    </form>
  );
}
