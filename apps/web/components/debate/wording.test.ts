// 완료 기준(grep): 디브리핑 전 지원자 화면·mock에 페르소나 유형과 옛 흐름(보드·분업·파트 문서·팀장·개인 알림)이 없고,
// 지원자 문구는 지원자 말("정할 항목"·"결정 사항"·"이걸로 정하기")을 쓴다(R7). 주석은 검사하지 않는다.
import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { expect, test } from "vitest";

const WEB = join(__dirname, "..", "..");
const HERE = __dirname;

/** 주석을 뺀 코드(문자열·JSX 글자만 남는다) */
function code(path: string) {
  return readFileSync(path, "utf8")
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .replace(/(^|[^:"'`])\/\/.*$/gm, "$1")
    .replace(/\{\/\*[\s\S]*?\*\/\}/g, "");
}

// 디브리핑 화면과 테스트, 개발 조작 패널을 뺀 지원자 컴포넌트
const SCREENS = readdirSync(HERE)
  .filter((f) => /\.tsx?$/.test(f) && !/\.test\./.test(f))
  .filter((f) => !["debrief-screen.tsx", "mock-controls.tsx"].includes(f))
  .map((f) => join(HERE, f));

const CANDIDATE_MOCKS = [
  "entry.json",
  "entry_completed.json",
  "state_pre_start.json",
  "state_keyword.json",
  "state_problem.json",
  "state_solution.json",
  "state_proposal.json",
  "debate_script.json",
  "materials.json",
  "material.json",
  "assistant_response.json",
  "proposal.json",
  "proposal_submit.json",
].map((f) => join(WEB, "mocks", "fixtures", f));

test("디브리핑 전 지원자 화면·mock에 페르소나 유형 이름이 없다", () => {
  const types = /stubborn|quiet|critic|agreeable|divergent|고집형|소극형|비판형/;
  for (const path of [...SCREENS, ...CANDIDATE_MOCKS]) {
    const text = path.endsWith(".json") ? readFileSync(path, "utf8") : code(path);
    expect(text, path).not.toMatch(types);
  }
});

test("옛 흐름 흔적(보드·분업·파트 문서·팀장·개인 알림·slot.filled)이 지원자 화면·mock에 없다", () => {
  const old =
    /board\.tsx|BoardColumn|division|my-docs|my_document|doc-viewer|manager|notices\.test|office_script|slot\.filled|팀장|파트 문서|주담당/;
  const mocks = ["debate.ts", "index.ts", "ws-replay.ts", "README.md"].map((f) =>
    join(WEB, "mocks", f),
  );
  for (const path of [...SCREENS, ...CANDIDATE_MOCKS, ...mocks]) {
    expect(readFileSync(path, "utf8"), path).not.toMatch(old);
  }
});

test("지원자 화면 문구에 내부 용어(칸·합의 패널·확정)가 없고 지원자 말을 쓴다", () => {
  // 기획안의 빈칸 경고 문구("비워 둔 칸")는 design.md가 정한 말이라 뺀다
  const all = SCREENS.map(code).join("\n").replaceAll("비워 둔 칸", "");
  expect(all).not.toMatch(/칸|합의 패널|확정/);
  expect(all).toContain("결정 사항");
  expect(all).toContain("이걸로 정하기");
  expect(all).toContain("지금 정할 항목");
});
