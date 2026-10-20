import { renderToStaticMarkup } from "react-dom/server";
import { expect, test } from "vitest";

import reportJson from "@/mocks/fixtures/admin/report.json";

import { ReportView, REPORT_NOTICE } from "./report-view";
import { changedAdjustments, missingMemos, phaseOf, previewTotal } from "./review";
import type { Report } from "./types";

const draft = reportJson as unknown as Report;

test("draft 리포트는 헤더 문구·산출물·평가표 입력을 보여 주고 합격·순위 UI가 없다", () => {
  const html = renderToStaticMarkup(<ReportView report={draft} onReview={() => {}} />);
  expect(html).toContain("검토 대기");
  expect(html).toContain("5/7 · 기록 없음 1");
  expect(html).toContain(REPORT_NOTICE);
  expect(html).toContain("① 산출물");
  expect(html).toContain("미작성");
  expect(html).toContain("② 요소별 관찰과 평가표");
  expect(html).toContain("실제 7.5분");
  // 섹션에 card_t_min이 없어도 근거의 context 값으로 카드 발생 시각을 보인다
  expect(html).toContain("카드 발생 48분");
  expect(html).toContain("판단 기준 없음, 면접 확인용");
  expect(html).toContain("담당자 값");
  expect(html).toContain("검토 완료</button>");
  expect(html).not.toMatch(/순위|등급|합격 가능/);
});

test("값을 바꾸고 메모가 없으면 막고, 확정 중과 final을 구분한다", () => {
  const changed = changedAdjustments(draft, {
    coop_replied_within_5m: { choice: "1", memo: "" },
    resp_told_team: { choice: "1", memo: "자동 값과 같음" },
  });
  expect(changed.map((a) => a.item_id)).toEqual(["coop_replied_within_5m"]);
  expect(missingMemos(changed)).toEqual(["coop_replied_within_5m"]);
  expect(previewTotal(draft, changed)).toEqual({ met: 6, judged: 7, no_record: 1 });

  const approving: Report = {
    ...draft,
    rubric: { ...draft.rubric, review: { memo: null, reviewed_at: null } },
  };
  expect(phaseOf(draft)).toBe("draft");
  expect(phaseOf(approving)).toBe("approving");
  const approvingHtml = renderToStaticMarkup(<ReportView report={approving} onReview={() => {}} />);
  expect(approvingHtml).toContain("확정 중…");

  const final: Report = {
    ...approving,
    stage: "final",
    reviewed_at: "2026-10-18T01:00:00+00:00",
    rubric: {
      ...approving.rubric,
      history: [
        {
          item_id: "coop_replied_within_5m",
          element: "cooperation",
          auto: 0,
          reviewer: 1,
          memo: "표시 시각만 늦었음",
          created_at: "2026-10-18T01:00:00+00:00",
        },
      ],
    },
  };
  const finalHtml = renderToStaticMarkup(<ReportView report={final} onReview={() => {}} />);
  expect(finalHtml).toContain("검토 완료 · final");
  expect(finalHtml).toContain("검토 이력");
  expect(finalHtml).toContain("표시 시각만 늦었음");
  expect(finalHtml).not.toContain("담당자 값");
});
