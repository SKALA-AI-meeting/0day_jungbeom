// 디브리핑. 세션 실패(failed_stage=session)면 연출을 드러내지 않고 중단 안내만 보인다(재응시 가능).
import { Card } from "@/components/ui";

import type { Debrief } from "./types";

export function DebriefScreen({ debrief, revisit }: { debrief: Debrief; revisit?: boolean }) {
  if (debrief.failed_stage === "session") {
    return (
      <main className="mx-auto flex max-w-2xl flex-col gap-4 px-6 py-16">
        <Card title="시스템 문제로 평가가 중단되었습니다">
          <p className="text-muted">채용 담당자에게 문의해 주세요.</p>
          <p className="mt-2 text-sm text-muted">{debrief.scoring_notice}</p>
        </Card>
      </main>
    );
  }
  return (
    <main className="mx-auto flex max-w-2xl flex-col gap-4 px-6 py-16">
      {revisit && <p className="text-sm text-muted">이미 완료된 평가입니다.</p>}
      <h1 className="text-2xl font-semibold">수고하셨습니다</h1>
      <p className="text-muted">과제 중에 있었던 상황이 무엇이었는지 알려 드립니다.</p>
      {debrief.events.map((event) => (
        <Card key={event.element} title={event.name}>
          <p>{event.description}</p>
          {event.rubric_items.length > 0 && (
            <>
              <p className="mt-3 text-sm font-medium">이 상황에서 살펴본 항목</p>
              <ul className="mt-1 list-disc pl-5 text-sm text-muted">
                {event.rubric_items.map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
            </>
          )}
        </Card>
      ))}
      {debrief.persona_note && (
        <Card title="함께 일한 동료">
          <p>{debrief.persona_note}</p>
        </Card>
      )}
      <Card title="기록과 점수">
        <p className="text-sm">{debrief.scoring_notice}</p>
      </Card>
    </main>
  );
}
