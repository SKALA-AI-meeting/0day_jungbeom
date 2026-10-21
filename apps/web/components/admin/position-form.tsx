"use client";

// 채용 건 생성: 이름과 세션 길이만 입력한다. 보는 요소 5개는 읽기 전용 안내이고 선택 UI가 없다(R2).
import Link from "next/link";
import { useState, type FormEvent } from "react";

import { Button, Input } from "@/components/ui";

import { Segmented } from "./segmented";
import type { Catalog, SessionMinutes } from "./types";

export const SAME_SCALE_NOTICE = "모든 채용 건이 같은 요소와 같은 척도로 기록됩니다.";

const MINUTES_LABEL: Record<SessionMinutes, string> = { 60: "60분", 15: "15분 (데모)" };

export type PositionFormProps = {
  catalog: Catalog;
  pending?: boolean;
  error?: string | null;
  onSubmit: (value: { name: string; session_minutes: SessionMinutes }) => void;
};

export function PositionForm({ catalog, pending, error, onSubmit }: PositionFormProps) {
  const [name, setName] = useState("");
  const [minutes, setMinutes] = useState<SessionMinutes>(catalog.default_session_minutes);
  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (!name.trim()) return;
    onSubmit({ name: name.trim(), session_minutes: minutes });
  };
  return (
    <form className="flex flex-col gap-10" onSubmit={submit}>
      <div className="flex flex-col gap-6">
        <Input
          label="채용 건 이름"
          value={name}
          onChange={(e) => setName(e.target.value)}
          maxLength={80}
          required
        />
        <div className="flex flex-col gap-1.5">
          <span className="text-sm font-medium">세션 길이</span>
          <Segmented
            label="세션 길이"
            value={minutes}
            onChange={setMinutes}
            options={catalog.session_minutes_options.map((m) => ({
              value: m,
              label: MINUTES_LABEL[m],
            }))}
          />
          <p className="text-sm text-muted">15분은 시연용으로 모든 시간을 같은 비율로 줄입니다.</p>
        </div>
      </div>

      <section aria-labelledby="elements-title" className="flex flex-col gap-3">
        <h2 id="elements-title" className="text-title3 font-semibold">
          보는 요소
        </h2>
        <ul className="divide-y divide-line border-y border-line">
          {catalog.elements.map((element) => (
            <li key={element.id} className="flex flex-col gap-1 py-4">
              <span className="font-semibold">{element.name}</span>
              <span className="text-ink">{element.meaning}</span>
              <span className="text-sm text-muted">이렇게 봅니다 · {element.how_we_see}</span>
            </li>
          ))}
        </ul>
        <p className="text-sm text-muted">
          {SAME_SCALE_NOTICE}{" "}
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
      <div>
        <Button type="submit" loading={pending} disabled={!name.trim()}>
          채용 건 만들기
        </Button>
      </div>
    </form>
  );
}
