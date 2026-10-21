// 완료 기준: 실 api(NEXT_PUBLIC_MOCK=0) 클라이언트가 계약 응답을 그대로 파싱하고 오류를 ApiError로 바꾼다.
// 응답 본문은 tests/fixtures/contracts/의 계약 픽스처(fetch만 가짜).
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { afterEach, expect, test, vi } from "vitest";

import type { Entry, StateSnapshot } from "@/components/debate/types";

import { api, ApiError, assetUrl, API_URL, MOCK } from "./api";

const contract = (name: string) =>
  JSON.parse(
    readFileSync(
      fileURLToPath(new URL(`../../../tests/fixtures/contracts/${name}.json`, import.meta.url)),
      "utf8",
    ),
  );

function stubFetch(status: number, body: unknown) {
  const fetchMock = vi.fn(async () => new Response(JSON.stringify(body), { status }));
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

afterEach(() => vi.unstubAllGlobals());

test("단위 테스트는 실 api 경로를 탄다(NEXT_PUBLIC_MOCK 꺼짐)", () => {
  expect(MOCK).toBe(false);
});

test("GET /s/{token}·/state: 계약 응답을 파싱하고 세션 토큰을 Authorization으로 보낸다", async () => {
  const fetchMock = stubFetch(200, contract("state_keyword"));
  const snap = await api<StateSnapshot>("/sessions/sess-1/state", { token: "jwt-1" });
  expect(snap.keyword_options.map((o) => o.option_key)).toEqual(["water", "fire", "tree", "wind"]);
  expect(snap.ws_seq).toBeGreaterThan(0);
  const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
  expect(url).toBe(`${API_URL}/sessions/sess-1/state`);
  expect((init.headers as Record<string, string>).Authorization).toBe("Bearer jwt-1");

  stubFetch(200, contract("entry"));
  const entry = await api<Entry>("/s/tok");
  expect(entry.session_id).toBe("sess-1");
});

test("POST 칸 확정: 계약 요청 본문을 JSON으로 보낸다", async () => {
  const fetchMock = stubFetch(200, contract("slot_confirm"));
  await api("/sessions/sess-1/slots/keyword/confirm", {
    method: "POST",
    token: "jwt-1",
    body: contract("slot_confirm_request"),
  });
  const [, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
  expect(init.method).toBe("POST");
  expect(JSON.parse(init.body as string)).toEqual({ value: "물", option_key: "water" });
});

test("오류 응답 {error:{code,message}}는 ApiError(status, code)로 바뀐다", async () => {
  stubFetch(409, contract("error"));
  const error = await api("/sessions/sess-1/slots/keyword/confirm", { method: "POST" }).catch(
    (e) => e,
  );
  expect(error).toBeInstanceOf(ApiError);
  expect(error).toMatchObject({ status: 409, code: "phase_not_open" });
});

test("avatar_url의 /assets 경로는 api 주소를 붙이고 다른 주소는 그대로 둔다", () => {
  expect(assetUrl("/assets/missions/debate/avatars/avatar-01.png")).toBe(
    `${API_URL}/assets/missions/debate/avatars/avatar-01.png`,
  );
  expect(assetUrl("https://cdn.example.com/a.png")).toBe("https://cdn.example.com/a.png");
});
