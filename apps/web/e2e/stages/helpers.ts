// 단계별 화면 테스트 공용: 내부 테스트 API로 시드 세션 만들기·시간 당기기, 스크린샷·내부 조회.
// 내부 토큰은 env(INTERNAL_TOKEN) 또는 infra/.env.e2e에서 읽고 출력하지 않는다.
import { type Page, expect, request } from "@playwright/test";
import { mkdirSync, readFileSync } from "node:fs";
import { join } from "node:path";

const REPO = join(import.meta.dirname, "..", "..", "..", "..");
export const RECORDS = join(REPO, "tests", "e2e", "records", "stages");
export const INTERNAL = process.env.E2E_INTERNAL_URL ?? "http://localhost:8101";
export const ADMIN = { email: "e2e@example.com", password: "e2e-password" };

function internalToken(): string {
  if (process.env.INTERNAL_TOKEN) return process.env.INTERNAL_TOKEN;
  for (const name of [".env.e2e", ".env.local", ".env"]) {
    try {
      const text = readFileSync(join(REPO, "infra", name), "utf8");
      const found = /^INTERNAL_TOKEN=(.+)$/m.exec(text)?.[1]?.trim();
      if (found) return found;
    } catch {
      // 다음 파일
    }
  }
  throw new Error("INTERNAL_TOKEN을 찾지 못했어요(env 또는 infra/.env.e2e)");
}

async function internal<T>(method: "GET" | "POST", path: string, data?: unknown): Promise<T> {
  const ctx = await request.newContext({
    baseURL: INTERNAL,
    extraHTTPHeaders: { "X-Internal-Token": internalToken() },
  });
  try {
    const response = await ctx.fetch(path, { method, data });
    if (!response.ok()) throw new Error(`${method} ${path} -> ${response.status()}`);
    return (await response.json()) as T;
  } finally {
    await ctx.dispose();
  }
}

export type Seed = {
  sessionId: string;
  /** 웹 기준 경로(/s/<token>) */
  link: string;
  sessionToken?: string;
  debriefToken?: string;
  adminReportPath?: string;
};

type StartAt = "entry" | "keyword" | "problem" | "solution" | "proposal" | "ended";

/** 시드 세션(15분). 초대 링크는 api가 web_base_url로 만들어 포트가 다르므로 경로만 쓴다 */
export async function seed(startAt: StartAt): Promise<Seed> {
  const made = await internal<{
    session_id: string;
    invite_url: string;
    session_token?: string;
    debrief_token?: string;
    admin_report_url?: string;
  }>("POST", "/internal/test/sessions", { session_minutes: 15, start_at: startAt });
  return {
    sessionId: made.session_id,
    link: new URL(made.invite_url).pathname,
    sessionToken: made.session_token,
    debriefToken: made.debrief_token,
    adminReportPath: made.admin_report_url ? new URL(made.admin_report_url).pathname : undefined,
  };
}

/** 시간 당기기(scripts/stage_advance.py와 같은 호출). 처리는 다음 스케줄러 틱이 한다 */
export async function advance(sessionId: string, to: string | number): Promise<void> {
  const body = typeof to === "number" ? { seconds: to } : { to };
  await internal("POST", `/internal/test/sessions/${sessionId}/advance`, body);
}

export function internalGet<T>(sessionId: string, path = ""): Promise<T> {
  return internal<T>("GET", `/internal/sessions/${sessionId}${path}`);
}

export async function shot(page: Page, stage: string, name: string): Promise<void> {
  const dir = join(RECORDS, stage);
  mkdirSync(dir, { recursive: true });
  await page.screenshot({ path: join(dir, `${name}.png`) });
}

/** 토론방에 지원자 메시지를 보내고 내 말풍선이 나타날 때까지 기다린다 */
export async function say(page: Page, text: string): Promise<void> {
  // 블록이 모두 보여 AI 어시스턴트의 [보내기]와 겹치므로 토론방 안에서 찾는다
  const chat = page.getByRole("region", { name: "토론방" });
  await chat.getByLabel("메시지 입력").fill(text);
  await chat.getByRole("button", { name: "보내기" }).click();
  await expect(page.getByRole("log").getByText(text)).toBeVisible();
}

/** 그리드 블록(결정 사항·자료·AI 어시스턴트·기획안)의 제목을 눌러 그 블록의 안 읽음 배지를 지운다 */
export async function tab(page: Page, label: string): Promise<void> {
  await page.getByRole("region", { name: label }).getByRole("heading", { name: label }).click();
}

/** 토론방(말풍선 영역) */
export const room = (page: Page) => page.getByRole("log");

/** AI 동료 응답이 가라앉을 때까지(메시지 수가 2.4초 동안 그대로). 연속 전송은 앞 응답을 버리게 하므로 사이에 쓴다 */
export async function settle(sessionId: string): Promise<void> {
  let last = -1;
  let stable = 0;
  for (let i = 0; i < 40 && stable < 2; i += 1) {
    const count = (await internalGet<unknown[]>(sessionId, "/messages")).length;
    stable = count === last ? stable + 1 : 0;
    last = count;
    await new Promise((resolve) => setTimeout(resolve, 1200));
  }
}
