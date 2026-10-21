// 완료 기준(리포트): 머리 안내·설계된 장면, 요약표 "수준 N (1~5)"(합계 없음), 타임라인, 차원 수준·확신도·근거,
// low 표시, 사유 5종, 기여 대조표, 사실 지표, 기획안, AI 활용, 차원 단위 조정(메모 필수)·요소 재계산·검토 완료·final 메모,
// "기록에서 보기" 하이라이트, 인쇄 때 차원 전부 펼침. 샘플 리포트 픽스처 요건.
import { renderToStaticMarkup } from "react-dom/server";
import { beforeEach, expect, test } from "vitest";

import sampleJson from "@/fixtures/sample-report.json";
import { adminMockRequest as mockRequest, resetAdminMock } from "@/mocks/admin";
import recordJson from "@/mocks/fixtures/admin_record.json";

import { NO_RECORD_TEXT } from "./format";
import { RecordView } from "./record-view";
import {
  AI_HEADER,
  DESIGNED_SCENE_NOTICE,
  FACTS_NOTE,
  REPORT_NOTICE,
  ReportView,
} from "./report-view";
import { elementLevel, phaseOf, recordAnchor, withEdits } from "./review";
import type { RecordEntry, Report } from "./types";

beforeEach(resetAdminMock);

const sample = sampleJson as unknown as Report;
const href = (ref: { type: string; id: string; t_min: number }) => `/r#${recordAnchor(ref)}`;
const get = (id = "sess-1") => mockRequest<Report>("GET", `/admin/sessions/${id}/report`);
const TOTAL = /총점|합계|점수/;
// 고정 안내문("합격·불합격·순위는 판정하지 않습니다")을 뺀 나머지에 판정 표현이 없어야 한다
const judged = (html: string) => /합격|(?<!우선)순위/.test(html.replace(REPORT_NOTICE, ""));

test("샘플 리포트 픽스처: 5요소·19차원, 사유 5종, 미발생 카드 1장, 조정 1개, 확신도 3종, 근거 4종", () => {
  expect(sample.elements).toHaveLength(5);
  expect(sample.dimensions).toHaveLength(19);
  const reasons = new Set(sample.dimensions.map((d) => d.no_record_reason).filter(Boolean));
  expect([...reasons].sort()).toEqual(Object.keys(NO_RECORD_TEXT).sort());
  expect(sample.cards).toHaveLength(6);
  expect(sample.cards.filter((c) => c.fired_at == null)).toHaveLength(1);
  expect(sample.dimensions.filter((d) => d.adjusted_level != null && d.adjust_memo)).toHaveLength(
    1,
  );
  expect(new Set(sample.dimensions.map((d) => d.confidence).filter(Boolean))).toEqual(
    new Set(["high", "medium", "low"]),
  );
  const kinds = new Set(sample.dimensions.flatMap((d) => d.evidence.map((e) => e.kind)));
  expect(kinds).toEqual(new Set(["message", "slot", "proposal", "contribution"]));
  for (const d of sample.dimensions) {
    if (d.level != null && d.level >= 4) {
      expect(d.evidence.filter((e) => e.counted).length).toBeGreaterThanOrEqual(2);
    }
  }
  // record_ref는 전체 기록 픽스처와 맞는다
  const anchors = new Set((recordJson as RecordEntry[]).map((e) => recordAnchor(e.ref)));
  for (const d of sample.dimensions) {
    for (const e of d.evidence) expect(anchors.has(recordAnchor(e.record_ref))).toBe(true);
  }
  expect(JSON.stringify(sample)).not.toMatch(/"total_score"|"sum"/);
});

test("샘플 리포트 화면: 사유 문장 5종, 미발생 카드, 담당자 조정 나란히, 조정·검토 UI 없음", () => {
  const html = renderToStaticMarkup(<ReportView report={sample} recordHref={href} sample />);
  for (const text of Object.values(NO_RECORD_TEXT)) expect(html).toContain(text);
  expect(html).toContain("이벤트 미발생");
  // 요약표 표시 설명, 판단 보류 개수, 판단 보류 차원 행의 원문 기록 링크
  expect(html).toContain("확신도 low로 판단한 차원 수");
  // 픽스처의 판단 보류 차원은 flexibility 하나뿐이다
  expect(html.match(/판단 보류 \d/g)).toEqual(["판단 보류 1"]);
  expect(html).toMatch(/href="\/r"[^>]*>원문 기록/);
  expect(html).toContain("담당자 조정됨");
  expect(html).toContain("메모 · 09:06 발언 앞뒤에서");
  expect(html).not.toContain("검토 완료");
  expect(html).not.toMatch(TOTAL);
  expect(judged(html)).toBe(false);
});

test("리포트 draft 렌더: 안내·요약·타임라인·차원·근거·사실·기획안·AI 활용", async () => {
  const draft = await get();
  expect(phaseOf(draft)).toBe("draft");
  const html = renderToStaticMarkup(
    <ReportView report={draft} recordHref={href} onReview={() => {}} />,
  );
  expect(html).toContain("검토 대기");
  expect(html).toContain(REPORT_NOTICE);
  expect(html).toContain(DESIGNED_SCENE_NOTICE);
  expect(html).toContain("설계된 장면");
  expect(html).toContain("고집형");
  expect(html).toContain("수준 3 (1~5)");
  expect(html).toContain("근거 약함, 원문 확인 권장");
  expect(html).toContain("확신도 높음");
  expect(html).toContain("해당 없음"); // hon_source_in_talk
  expect(html).toContain("최초 제안자");
  expect(html).toContain("시간 초과");
  expect(html).toContain("기여 대조표");
  expect(html).toContain(FACTS_NOTE);
  expect(html).toContain("아이디어 기여");
  expect(html).toContain(AI_HEADER);
  expect(html).toContain("도심 침수 사례"); // 인용 자료 제목
  expect(html).toContain("맥락"); // AI 동료 메시지 근거
  expect(html).toContain("09:03"); // 오피스 시각(60분 세션 t_min 3.6)
  expect(html).toContain('href="/r#message-m-06"');
  expect(html).not.toMatch(/<details[^>]* open=""/); // 차원은 접힘이 기본
  expect(html).not.toMatch(TOTAL);
  expect(judged(html)).toBe(false);

  // 인쇄 미리보기: 19개 차원 전부 펼침, 조정 버튼은 no-print
  const printed = renderToStaticMarkup(<ReportView report={draft} recordHref={href} printing />);
  expect(printed.match(/<details[^>]* open=""/g)).toHaveLength(19);
});

test("차원 조정은 메모 필수, 요소 수준 재계산, 검토 완료 → 확정 중 → final → 메모 추가", async () => {
  const draft = await get();
  // 화면 편집 반영 요소 수준: 경쟁 안 비교 2 → 4면 설득 (3+3+4+4)/4 = 3.5 → 4
  const edited = withEdits(draft.dimensions, {
    pers_comparison: { level: 4, reason: null, memo: "근거 있음" },
  });
  expect(elementLevel(draft.dimensions, "persuasion")).toBe(3);
  expect(elementLevel(edited, "persuasion")).toBe(4);

  await expect(
    mockRequest("POST", "/admin/sessions/sess-1/review", {
      reviewer_name: "박채용",
      adjustments: [{ dimension_id: "pers_comparison", level: 4, memo: " " }],
    }),
  ).rejects.toMatchObject({ code: "memo_required" });
  await expect(
    mockRequest("POST", "/admin/sessions/sess-1/review", { reviewer_name: "", adjustments: [] }),
  ).rejects.toMatchObject({ code: "invalid_input" });

  const body = {
    reviewer_name: "박채용",
    adjustments: [
      { dimension_id: "pers_comparison", level: 4, memo: "실현 가능성 비교도 함" },
      {
        dimension_id: "incl_shared_decision",
        level: null,
        no_record_reason: "not_applicable",
        memo: "확인할 장면이 없었음",
      },
    ],
  };
  expect(await mockRequest("POST", "/admin/sessions/sess-1/review", body)).toEqual({
    status: "approving",
  });
  const approving = await get();
  expect(phaseOf(approving)).toBe("approving");
  expect(approving.elements.find((e) => e.element === "persuasion")?.adjusted_level).toBe(4);
  const html = renderToStaticMarkup(<ReportView report={approving} recordHref={href} />);
  expect(html).toContain("담당자 조정됨");
  expect(html).toContain("확정 중");

  // 다른 본문 재요청은 409
  await expect(
    mockRequest("POST", "/admin/sessions/sess-1/review", { ...body, adjustments: [] }),
  ).rejects.toMatchObject({ code: "already_reviewed" });

  const final = await get();
  expect(phaseOf(final)).toBe("final");
  const notes = await mockRequest<{ notes: unknown[] }>(
    "POST",
    "/admin/sessions/sess-1/report/notes",
    {
      text: "2차 면접에서 확인",
      reviewer_name: "박채용",
    },
  );
  expect(notes.notes).toHaveLength(1);
  const finalHtml = renderToStaticMarkup(
    <ReportView report={await get()} recordHref={href} onAddNote={() => {}} />,
  );
  expect(finalHtml).toContain("검토 완료");
  expect(finalHtml).toContain("2차 면접에서 확인");
  expect(finalHtml).toContain("메모 추가");
});

test("전체 기록: 근거 앵커 줄 하이라이트, 오피스 시각, 단계·결과 한국어", () => {
  const html = renderToStaticMarkup(
    <RecordView
      entries={recordJson as RecordEntry[]}
      seats={sample.seats}
      sessionMinutes={60}
      backHref="/admin/sample-report"
      highlight="message-m-06"
    />,
  );
  expect(html).toMatch(/id="message-m-06" aria-current="true"/);
  expect(html).toContain("리포트로 돌아가기");
  expect(html).toContain("키워드 확정: 물 · 지원자 결정");
  expect(html).toContain("자료 열람: 지역별 물 부족 통계");
  expect(html).toContain("09:46");
});

test("사실 지표에 제출 때 빈 칸과 빈칸 경고 확인이 나오고, 칸 결과는 outcome으로 보인다", () => {
  const r: Report = {
    ...sample,
    facts: { ...sample.facts, blank_sections_at_submit: ["rationale", "idea_credit"] },
    slots: sample.slots.map((s) => ({
      ...s,
      resolution: "consensus",
      outcome: "candidate_decision",
    })),
  };
  (r.facts as Record<string, unknown>).blank_warning_acknowledged = null;
  const html = renderToStaticMarkup(<ReportView report={r} recordHref={href} sample />);
  expect(html).toContain("근거 · 아이디어 기여");
  expect(html).toContain("자동 제출");
  expect(html).toContain("지원자 결정");
});
