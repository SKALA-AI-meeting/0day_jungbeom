import { renderToStaticMarkup } from "react-dom/server";
import { expect, test } from "vitest";

import candidatesJson from "@/mocks/fixtures/admin/candidates.json";
import catalogJson from "@/mocks/fixtures/admin/catalog.json";

import { CandidateTable, InvitePanel } from "./candidates";
import type { Candidate, Catalog } from "./types";

const names = new Map((catalogJson as unknown as Catalog).elements.map((e) => [e.id, e.name]));

test("지원자 목록은 상태 7종 이상과 합계·요소별 칩을 보여 주고 초대 폼에 복사 버튼이 붙는다", () => {
  const html = renderToStaticMarkup(
    <CandidateTable
      candidates={candidatesJson as Candidate[]}
      names={names}
      onCancel={() => {}}
      onReinvite={() => {}}
    />,
  );
  for (const label of [
    "초대됨",
    "만료",
    "취소",
    "진행 중",
    "완료",
    "리포트 준비됨",
    "확정 중",
    "검토 완료",
    "실패",
  ]) {
    expect(html).toContain(label);
  }
  expect(html).toContain("5/7 · 기록 없음 1");
  expect(html).toContain("기본 점수");
  expect(html).toContain("담당자 점수");
  expect(html).toContain("협력 태도 2/3");
  expect(html).toContain("–/0");
  // 실패·만료·취소 3행은 다시 초대할 수 있다
  expect(html.match(/다시 초대/g)).toHaveLength(4);
  expect(html).not.toMatch(/합격|순위|등급/);

  const invite = renderToStaticMarkup(
    <InvitePanel
      onInvite={() => {}}
      result={{
        session_id: "s-1",
        invite_url: "http://localhost:3000/s/abc",
        expires_at: "2026-10-23T01:00:00+00:00",
        notice_text: "안내",
      }}
    />,
  );
  expect(invite).toContain("http://localhost:3000/s/abc");
  expect(invite).toContain("링크 복사");
  expect(invite).toContain("안내 문안 복사");
});
