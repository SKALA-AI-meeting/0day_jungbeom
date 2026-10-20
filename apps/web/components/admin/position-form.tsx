"use client";

// 채용 건 생성: 미션 1개 표시(선택 없음), 요소 카드 5장(기본 전체 선택, 체크 해제로 뺌, 뺀 카드에 차이 한 줄).
// 상황·시점·평가표 항목은 보여 주지 않는다(docs/frontend/design.md "관리자 생성 화면").
import Link from "next/link";
import { useState, type FormEvent } from "react";

import { Button, Card, cn, Input } from "@/components/ui";

import type { Catalog, ElementId } from "./types";

export const SAME_BASIS_LINE =
  "요소 구성이 같은 채용 건끼리만 같은 기준 · 구성이 다르면 만점도 다름";

/** 뺀 요소마다 달라지는 것 한 줄(카탈로그의 if_unselected) */
export function unselectedLines(catalog: Catalog, selected: ElementId[]) {
  return catalog.elements
    .filter((e) => !selected.includes(e.id))
    .map((e) => ({ id: e.id, line: e.if_unselected }));
}

export function PositionForm({
  catalog,
  pending,
  error,
  onSubmit,
}: {
  catalog: Catalog;
  pending?: boolean;
  error?: string | null;
  onSubmit: (value: { name: string; elements: ElementId[]; mission_id: string }) => void;
}) {
  const mission = catalog.missions[0];
  const [name, setName] = useState("");
  const [selected, setSelected] = useState<ElementId[]>(catalog.elements.map((e) => e.id));
  const off = new Map(unselectedLines(catalog, selected).map((u) => [u.id, u.line]));

  const toggle = (id: ElementId) =>
    setSelected((cur) => (cur.includes(id) ? cur.filter((x) => x !== id) : [...cur, id]));

  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (selected.length === 0) return;
    // 카탈로그 순서대로 보낸다
    onSubmit({
      name,
      mission_id: mission.id,
      elements: catalog.elements.map((e) => e.id).filter((id) => selected.includes(id)),
    });
  };

  return (
    <form className="flex flex-col gap-6" onSubmit={submit}>
      <Card>
        <Input
          label="채용 건 이름"
          placeholder="예: PM 인턴 2026 하반기"
          value={name}
          onChange={(e) => setName(e.target.value)}
          required
        />
      </Card>

      <section className="flex flex-col gap-2">
        <h2 className="text-lg font-semibold">미션</h2>
        <div className="rounded-lg border border-line bg-surface px-5 py-4">
          <p className="font-semibold">{mission.name}</p>
          <p className="text-sm text-muted">
            {mission.company_name} · {catalog.session_minutes}분 · 산출물 {mission.deliverable}
          </p>
        </div>
      </section>

      <section className="flex flex-col gap-3">
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <h2 className="text-lg font-semibold">관찰 요소</h2>
          <span className="text-sm text-muted">{selected.length}/5 선택 · 체크 해제로 제외</span>
        </div>
        <ul className="grid grid-cols-1 gap-3 md:grid-cols-2">
          {catalog.elements.map((element) => {
            const on = selected.includes(element.id);
            return (
              <li key={element.id}>
                <label
                  className={cn(
                    "flex h-full cursor-pointer gap-3 rounded-lg border bg-surface px-4 py-4 transition-colors",
                    on ? "border-accent/50" : "border-line bg-surface-sunken/60",
                  )}
                >
                  <input
                    type="checkbox"
                    checked={on}
                    onChange={() => toggle(element.id)}
                    className="mt-1 size-4 shrink-0 accent-[var(--color-accent)]"
                  />
                  <span className="flex min-w-0 flex-1 flex-col gap-2">
                    <span className={cn("font-semibold", !on && "text-muted")}>{element.name}</span>
                    {/* 라벨은 제품 UI처럼 명사형. 값 문구는 카탈로그(서버)에서 온다 */}
                    <dl className="grid grid-cols-[64px_1fr] gap-x-2 gap-y-1 text-sm">
                      <dt className="text-xs leading-5 text-subtle">한 줄 설명</dt>
                      <dd>{element.meaning}</dd>
                      <dt className="text-xs leading-5 text-subtle">관찰 기준</dt>
                      <dd className="text-muted">{element.how_we_see}</dd>
                      {!on && (
                        <>
                          <dt className="text-xs leading-5 text-warning">미선택 시</dt>
                          <dd className="rounded-sm bg-warning-soft px-1.5">
                            {off.get(element.id)}
                          </dd>
                        </>
                      )}
                    </dl>
                  </span>
                </label>
              </li>
            );
          })}
        </ul>
        <p className="text-sm text-muted">
          {SAME_BASIS_LINE}{" "}
          <Link
            href="/admin/sample-report"
            className="text-accent underline-offset-4 hover:underline"
          >
            샘플 리포트 보기
          </Link>
        </p>
      </section>

      {error && (
        <p role="alert" className="text-sm text-danger">
          {error}
        </p>
      )}
      <div className="flex items-center gap-3">
        <Button type="submit" loading={pending} disabled={selected.length === 0}>
          채용 건 만들기
        </Button>
        {selected.length === 0 && <span className="text-sm text-danger">요소 1개 이상 필요</span>}
      </div>
    </form>
  );
}
