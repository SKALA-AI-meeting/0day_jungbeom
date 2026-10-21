"use client";

// 디브리핑: 한 열 문서. R1 첫 문장 → 이의 제기 경로 → 장면(카드) 설명 → 보는 요소 → 내 발언 돌아보기 →
// AI 동료 소개(여기서 처음 성향이 드러난다) → 결과를 보이지 않는 이유·기업이 보는 것·보관 → 기획안 열람 → 설문.
// 척도 세부·수준은 보이지 않는다.
import { Copy } from "lucide-react";
import { useState, type ReactNode } from "react";

import { Avatar, Button, Wordmark, cn, toast } from "@/components/ui";

import { SECTION_META } from "./proposal-editor";
import { PHASE_LABEL, officeTime } from "./state";
import { SECTION_IDS, type Debrief, type EndReason, type Seat } from "./types";

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="flex flex-col gap-4 border-t border-line pt-8">
      <h2 className="text-title2 font-semibold">{title}</h2>
      {children}
    </section>
  );
}

function Scale({
  value,
  disabled,
  onChange,
  label,
}: {
  value: number | null;
  disabled: boolean;
  onChange: (value: number) => void;
  label: string;
}) {
  return (
    <div
      role="radiogroup"
      aria-label={label}
      className="flex w-fit rounded-md bg-surface-sunken p-0.5"
    >
      {[1, 2, 3, 4, 5].map((n) => (
        <button
          key={n}
          type="button"
          role="radio"
          aria-checked={value === n}
          disabled={disabled}
          onClick={() => onChange(n)}
          className={cn(
            "w-12 rounded-[calc(var(--radius-md)-2px)] py-1.5 text-body tabular-nums",
            value === n
              ? "border border-line bg-surface font-semibold"
              : "border border-transparent text-muted",
          )}
        >
          {n}
        </button>
      ))}
    </div>
  );
}

function Survey({
  survey,
  onSubmit,
}: {
  survey: Debrief["survey"];
  onSubmit: (answers: { q: string; value: number }[], comment: string) => Promise<boolean>;
}) {
  const [answers, setAnswers] = useState<Record<string, number>>({});
  const [comment, setComment] = useState("");
  const [done, setDone] = useState(survey.submitted);
  const [pending, setPending] = useState(false);
  if (done) return <p className="text-muted">설문에 답해 주셔서 고마워요.</p>;
  return (
    <div className="flex flex-col gap-5">
      {survey.questions.map((q) =>
        q.kind === "scale" ? (
          <div key={q.q} className="flex flex-col gap-2">
            <p className="text-body">{q.text}</p>
            <Scale
              label={q.text}
              value={answers[q.q] ?? null}
              disabled={pending}
              onChange={(value) => setAnswers((prev) => ({ ...prev, [q.q]: value }))}
            />
            <p className="text-caption text-muted">1 전혀 아니다 · 5 매우 그렇다</p>
          </div>
        ) : (
          <label key={q.q} className="flex flex-col gap-2">
            <span className="text-body">{q.text}</span>
            <textarea
              rows={3}
              maxLength={500}
              value={comment}
              onChange={(event) => setComment(event.target.value)}
              className="resize-none rounded-md border border-line bg-surface px-3 py-2 text-body outline-none focus-visible:border-accent"
            />
          </label>
        ),
      )}
      <p className="text-caption text-muted">모든 문항은 건너뛸 수 있고, 한 번만 보낼 수 있어요.</p>
      <div>
        <Button
          variant="secondary"
          loading={pending}
          onClick={async () => {
            setPending(true);
            const ok = await onSubmit(
              Object.entries(answers).map(([q, value]) => ({ q, value })),
              comment.trim(),
            );
            setPending(false);
            if (ok) setDone(true);
          }}
        >
          설문 보내기
        </Button>
      </div>
    </div>
  );
}

export function DebriefScreen({
  debrief,
  endReason,
  sessionMinutes,
  onSurvey,
}: {
  debrief: Debrief;
  endReason: EndReason | null;
  sessionMinutes: number;
  onSurvey: (answers: { q: string; value: number }[], comment: string) => Promise<boolean>;
}) {
  const failed = !!debrief.failed_stage;
  const elementName = new Map(debrief.elements?.map((e) => [e.element, e]) ?? []);
  return (
    <main className="mx-auto flex max-w-2xl flex-col gap-8 px-6 py-16">
      <Wordmark className="h-5 self-start" />
      <header className="flex flex-col gap-3">
        <h1 className="text-large font-bold">{failed ? "세션이 중단됐어요" : "수고하셨습니다"}</h1>
        {endReason === "timeout" && !failed && (
          <p className="text-callout text-muted">시간이 끝나 지금 상태로 제출됐어요.</p>
        )}
        <p className="text-callout leading-relaxed">{debrief.intro_notice}</p>
        <p className="text-body text-muted">{debrief.appeal_contact}</p>
      </header>

      {failed ? (
        <>
          <p className="text-body">담당자가 새 링크를 보낼 수 있습니다. {debrief.scoring_notice}</p>
          <p className="text-footnote text-muted">문의: {debrief.contact_email}</p>
        </>
      ) : (
        <>
          {!!debrief.cards?.length && (
            <Section title="이번 세션의 장면">
              <ul className="flex flex-col divide-y divide-line">
                {debrief.cards.map((card) => {
                  const element = elementName.get(card.element);
                  return (
                    <li key={card.card_id} className="flex flex-col gap-1 py-4 first:pt-0">
                      <p className="text-body">{card.description}</p>
                      {element && (
                        <p className="text-footnote text-muted">
                          {element.name} · {element.how_we_see}
                        </p>
                      )}
                    </li>
                  );
                })}
              </ul>
            </Section>
          )}

          {!!debrief.elements?.length && (
            <Section title="보는 요소">
              <ul className="flex flex-col divide-y divide-line">
                {debrief.elements.map((e) => (
                  <li key={e.element} className="flex flex-col gap-0.5 py-3 first:pt-0">
                    <p className="text-body font-semibold">{e.name}</p>
                    <p className="text-footnote text-muted">{e.how_we_see}</p>
                  </li>
                ))}
              </ul>
            </Section>
          )}

          {!!debrief.my_messages?.length && (
            <Section title="내 발언 돌아보기">
              <ul className="flex flex-col gap-4">
                {debrief.my_messages.map((m) => (
                  <li key={m.id} className="flex flex-col items-end gap-1">
                    <p className="text-caption text-muted tabular-nums">
                      {PHASE_LABEL[m.phase]} · {officeTime(m.t_min, sessionMinutes)}
                    </p>
                    <p className="max-w-[85%] rounded-bubble bg-bubble-candidate px-3.5 py-2 text-body text-on-bubble-candidate">
                      {m.content}
                    </p>
                  </li>
                ))}
              </ul>
            </Section>
          )}

          {!!debrief.seats?.length && (
            <Section title="함께한 AI 동료">
              <ul className="flex flex-col divide-y divide-line">
                {debrief.seats
                  .filter((s) => s.seat !== "candidate")
                  .map((s) => (
                    <li key={s.seat} className="flex gap-3 py-4 first:pt-0">
                      <Avatar
                        size={36}
                        seat={s.seat as Seat}
                        src={s.avatar_url}
                        name={s.display_name}
                      />
                      <div className="flex flex-col gap-0.5">
                        <p className="text-body font-semibold">{s.display_name}</p>
                        <p className="text-body text-muted">{s.persona_description}</p>
                      </div>
                    </li>
                  ))}
              </ul>
            </Section>
          )}

          <Section title="평가와 기록">
            <ul className="flex flex-col gap-2 text-body">
              <li>{debrief.scoring_notice}</li>
              <li>{debrief.retention_notice}</li>
              {debrief.connection_gaps.length > 0 && (
                <li>연결이 끊긴 구간이 있었어요. 불편이 있었다면 담당자에게 알려 주세요.</li>
              )}
              <li className="text-muted">문의: {debrief.contact_email}</li>
            </ul>
          </Section>

          {debrief.proposal && (
            <Section title="제출한 기획안">
              <p className="text-footnote text-muted">
                {new Date(debrief.view_until).toLocaleDateString("ko-KR")}까지 다시 볼 수 있어요.
              </p>
              <dl className="flex flex-col gap-4">
                {SECTION_IDS.map((id) => (
                  <div key={id} className="flex flex-col gap-1">
                    <dt className="text-footnote font-semibold text-muted">
                      {SECTION_META[id].title}
                    </dt>
                    <dd className="text-body break-words whitespace-pre-wrap">
                      {debrief.proposal!.sections[id] || "—"}
                    </dd>
                  </div>
                ))}
              </dl>
              <div>
                <Button
                  size="sm"
                  variant="secondary"
                  onClick={() => {
                    const text = SECTION_IDS.map(
                      (id) => `${SECTION_META[id].title}\n${debrief.proposal!.sections[id]}`,
                    ).join("\n\n");
                    void navigator.clipboard?.writeText(text);
                    toast("복사했어요");
                  }}
                >
                  <Copy size={14} aria-hidden /> 복사
                </Button>
              </div>
            </Section>
          )}

          <Section title="종료 설문">
            <Survey survey={debrief.survey} onSubmit={onSurvey} />
          </Section>
        </>
      )}
    </main>
  );
}
