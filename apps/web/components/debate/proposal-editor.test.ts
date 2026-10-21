import { expect, test } from "vitest";

import { blankSections, savedLabel, submitBody, submitFlow } from "./proposal-editor";
import { SECTION_IDS, type Sections } from "./types";

test("저장 표시는 실제 시계 없이 상대 표기만 쓴다", () => {
  const t = Date.UTC(2026, 9, 21, 8, 26, 9);
  expect(savedLabel(t, t + 10_000)).toBe("방금 저장됨");
  expect(savedLabel(t, t + 3 * 60_000)).toBe("3분 전 저장됨");
  expect(savedLabel(t, t + 2 * 3_600_000)).toBe("저장됨");
});

test("공백뿐인 칸만 빈 칸으로 세고, 제출 본문은 경고를 거쳤을 때만 blank_warning_shown을 담는다", () => {
  const filled = Object.fromEntries(SECTION_IDS.map((id) => [id, "내용"])) as Sections;
  expect(blankSections(filled)).toEqual([]);
  expect(blankSections({ ...filled, rationale: "  \n ", idea_credit: "" })).toEqual([
    "근거",
    "아이디어 기여",
  ]);
  expect(submitBody(false)).toEqual({});
  expect(submitBody(true)).toEqual({ blank_warning_shown: true });
});

function flow(latest: Sections | null, answers: { blank?: boolean; confirm?: boolean } = {}) {
  const calls: string[] = [];
  const steps = {
    prepare: async () => {
      calls.push("prepare");
      return latest;
    },
    askBlank: async (names: string[]) => {
      calls.push(`blank:${names.join(",")}`);
      return answers.blank ?? true;
    },
    askConfirm: async () => {
      calls.push("confirm");
      return answers.confirm ?? true;
    },
    submit: async (warned: boolean) => {
      calls.push(`submit:${warned}`);
    },
  };
  return { calls, run: () => submitFlow(steps) };
}

const full = Object.fromEntries(SECTION_IDS.map((id) => [id, "내용"])) as Sections;

test("빈 칸이 없으면 경고 없이 확인 창 뒤 제출한다", async () => {
  const f = flow(full);
  await f.run();
  expect(f.calls).toEqual(["prepare", "confirm", "submit:false"]);
});

test("빈 칸이 있으면 경고 → 확인 창 → blank_warning_shown 제출", async () => {
  const f = flow({ ...full, rationale: " " });
  await f.run();
  expect(f.calls).toEqual(["prepare", "blank:근거", "confirm", "submit:true"]);
});

test("[돌아가서 쓰기]나 확인 창 취소면 submit을 부르지 않는다", async () => {
  const back = flow({ ...full, rationale: "" }, { blank: false });
  await back.run();
  expect(back.calls).toEqual(["prepare", "blank:근거"]);
  const cancel = flow(full, { confirm: false });
  await cancel.run();
  expect(cancel.calls).toEqual(["prepare", "confirm"]);
  const unsaved = flow(null);
  await unsaved.run();
  expect(unsaved.calls).toEqual(["prepare"]);
});

test("저장(409 포함) 뒤 돌려받은 최신 초안으로 빈 칸을 다시 검사한다", async () => {
  // 화면 초안은 다 찼지만 409로 바뀐 최신 초안에는 빈 칸이 있는 경우: prepare가 준 값만 검사한다
  const f = flow({ ...full, expected_effect: "" });
  await f.run();
  expect(f.calls).toEqual(["prepare", "blank:기대효과", "confirm", "submit:true"]);
});
