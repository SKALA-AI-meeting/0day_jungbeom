"use client";

// 디브리핑: 연출이었던 장면과 살펴본 항목, 결과를 보여 주지 않는 이유, 최종본 열람·복사(7일), 종료 설문 2문항, 문의 창구.
// 세션 실패(failed_stage=session)면 연출 설명 없이 중단 안내만 보여 준다(contracts).
import { useState } from "react";

import { Button, Card, cn } from "@/components/ui";

import { copyText } from "./assistant-panel";
import { gapLine } from "./lines";
import type { Debrief } from "./types";

export const REMOTE_CONTEXT = "리모트에서는 응답 시점이 곧 상태 공유입니다.";

function dateText(iso: string | null) {
  if (!iso) return "";
  const d = new Date(iso);
  return `${d.getMonth() + 1}월 ${d.getDate()}일`;
}

function Survey({
  debrief,
  onSubmit,
}: {
  debrief: Debrief;
  onSubmit: (answers: { q: string; value: number }[]) => Promise<void>;
}) {
  const [values, setValues] = useState<Record<string, number>>({});
  const [done, setDone] = useState(debrief.survey.submitted);
  const [skipped, setSkipped] = useState(false);
  const [pending, setPending] = useState(false);
  if (done) return <p className="text-muted">설문 제출 완료 · 감사합니다</p>;
  if (skipped) return <p className="text-muted">설문 건너뜀</p>;
  return (
    <div className="flex flex-col gap-4">
      {debrief.survey.questions.map((question) => (
        <fieldset key={question.q} className="flex flex-col gap-2">
          <legend className="mb-1 text-base">{question.text}</legend>
          <div className="flex items-center gap-1.5">
            <span className="text-xs text-subtle">전혀 아니다</span>
            {[1, 2, 3, 4, 5].map((n) => (
              <button
                key={n}
                type="button"
                aria-pressed={values[question.q] === n}
                onClick={() => setValues((v) => ({ ...v, [question.q]: n }))}
                className={cn(
                  "press size-9 rounded-md border text-sm tabular-nums",
                  values[question.q] === n
                    ? "border-accent bg-accent text-white"
                    : "border-line bg-surface hover:bg-surface-sunken",
                )}
              >
                {n}
              </button>
            ))}
            <span className="text-xs text-subtle">매우 그렇다</span>
          </div>
        </fieldset>
      ))}
      <div className="flex gap-2">
        <Button
          loading={pending}
          disabled={Object.keys(values).length === 0}
          onClick={async () => {
            setPending(true);
            try {
              await onSubmit(Object.entries(values).map(([q, value]) => ({ q, value })));
              setDone(true);
            } finally {
              setPending(false);
            }
          }}
        >
          설문 보내기
        </Button>
        <Button variant="ghost" onClick={() => setSkipped(true)}>
          건너뛰기
        </Button>
      </div>
    </div>
  );
}

export function DebriefScreen({
  debrief,
  revisit,
  contactEmail,
  onSurvey,
}: {
  debrief: Debrief;
  revisit?: boolean;
  /** 디브리핑에 연락처가 없을 때(세션 실패) 입장 정보의 담당자 이메일 */
  contactEmail?: string;
  onSurvey: (answers: { q: string; value: number }[]) => Promise<void>;
}) {
  const contact = debrief.contact_email ?? contactEmail;
  const contactLine = contact ? (
    <a className="text-accent underline-offset-4 hover:underline" href={`mailto:${contact}`}>
      {contact}
    </a>
  ) : (
    "채용 담당자"
  );

  if (debrief.failed_stage === "session") {
    return (
      <main className="mx-auto flex min-h-dvh max-w-xl flex-col justify-center gap-5 px-6 py-16">
        <p className="text-sm font-semibold text-subtle">Day Zero</p>
        <h1 className="text-2xl font-semibold">세션 중단</h1>
        <p className="text-base">{debrief.scoring_notice}</p>
        <p className="text-muted">문의: {contactLine}</p>
      </main>
    );
  }

  const gaps = debrief.connection_gaps ?? [];
  return (
    <main className="mx-auto flex max-w-2xl flex-col gap-6 px-6 py-16">
      <p className="text-sm font-semibold text-subtle">Day Zero</p>
      <div className="flex flex-col gap-2">
        <h1 className="text-2xl font-semibold">수고하셨습니다</h1>
        <p className="text-muted">
          {revisit ? "마무리 안내 다시 보기 · " : ""}아래 장면은 모두 미리 준비된 연출입니다.
        </p>
      </div>

      {debrief.events.length > 0 && (
        <section className="flex flex-col gap-3">
          <h2 className="text-lg font-semibold">연출 장면</h2>
          {debrief.events.map((event) => (
            <Card key={event.card_id} className="flex flex-col gap-2">
              <h3 className="font-semibold">{event.name}</h3>
              <p className="text-base">{event.description}</p>
              <p className="text-sm text-muted">이 상황에서 살펴본 항목</p>
              <ul className="flex list-disc flex-col gap-1 pl-5 text-sm">
                {event.rubric_items.map((item) => (
                  <li key={item}>
                    {item.replace(" (pilot_value)", "")}
                    {/10분 안|5분 안/.test(item) && (
                      <span className="text-muted"> · {REMOTE_CONTEXT}</span>
                    )}
                  </li>
                ))}
              </ul>
            </Card>
          ))}
        </section>
      )}

      <section className="flex flex-col gap-2 rounded-lg bg-surface-sunken px-5 py-4">
        <h2 className="font-semibold">결과를 숫자로 보여 드리지 않는 이유</h2>
        <p className="text-base">{debrief.scoring_notice}</p>
        {debrief.persona_note && <p className="text-base">{debrief.persona_note}</p>}
        {debrief.retention_notice && (
          <p className="text-sm text-muted">{debrief.retention_notice}</p>
        )}
      </section>

      {debrief.final && (
        <section className="flex flex-col gap-3">
          <div className="flex items-baseline gap-2">
            <h2 className="text-lg font-semibold">내가 제출한 최종본</h2>
            {debrief.final_view_until && (
              <span className="text-sm text-muted">
                {dateText(debrief.final_view_until)}까지 볼 수 있어요
              </span>
            )}
            <Button
              size="sm"
              variant="secondary"
              className="ml-auto"
              onClick={() =>
                void copyText(
                  debrief
                    .final!.sections.map((s) => `${s.part_no}. ${s.title}\n${s.content}`)
                    .join("\n\n"),
                )
              }
            >
              전체 복사
            </Button>
          </div>
          <Card className="flex flex-col divide-y divide-line p-0">
            {debrief.final.sections.map((s) => (
              <article key={s.part_no} className="px-5 py-4">
                <h3 className="mb-1 text-sm font-semibold">
                  {s.part_no}. {s.title}
                </h3>
                <p className="text-base whitespace-pre-wrap text-ink">
                  {s.content || <span className="text-subtle">비어 있음</span>}
                </p>
              </article>
            ))}
          </Card>
        </section>
      )}

      {debrief.survey.questions.length > 0 && (
        <section className="flex flex-col gap-3">
          <h2 className="text-lg font-semibold">짧은 설문 (선택)</h2>
          <Survey debrief={debrief} onSubmit={onSurvey} />
        </section>
      )}

      <section className="flex flex-col gap-1 border-t border-line pt-5 text-sm text-muted">
        <p>문의·이의 제기: {contactLine}</p>
        {gaps.length > 0 ? (
          <p>
            기록된 연결 끊김:{" "}
            {gaps
              .map((g) => gapLine(g.from_t_min, g.to_t_min).replace(" 연결이 끊겼어요", ""))
              .join(", ")}{" "}
            · 사정이 있었다면 담당자에게 알려 주세요
          </p>
        ) : (
          <p>접속이 끊긴 구간이 있었다면 담당자에게 알려 주세요</p>
        )}
      </section>
    </main>
  );
}
