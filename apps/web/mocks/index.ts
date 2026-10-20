// NEXT_PUBLIC_MOCK=1일 때 lib/api.ts가 부르는 mock 라우터(foundation 소유).
// 경로 표는 화면 트랙이 각자 소유한 admin.ts(web-admin)·office.ts(web-office)에 있고, 여기서는 합치기만 한다.
// 없는 경로는 404 오류로 알린다.
import { ROUTES as ADMIN_ROUTES } from "./admin";
import { ROUTES as OFFICE_ROUTES } from "./office";
import type { MockRoute } from "./types";

const ROUTES: MockRoute[] = [...ADMIN_ROUTES, ...OFFICE_ROUTES];

function match(pattern: string, path: string): Record<string, string> | null {
  const want = pattern.split("/");
  const got = path.split("?")[0].split("/");
  if (want.length !== got.length) return null;
  const params: Record<string, string> = {};
  for (let i = 0; i < want.length; i += 1) {
    if (want[i].startsWith(":")) params[want[i].slice(1)] = decodeURIComponent(got[i]);
    else if (want[i] !== got[i]) return null;
  }
  return params;
}

export class MockMissingError extends Error {
  readonly status = 404;
  readonly code = "mock_missing";
}

export async function mockRequest<T>(method: string, path: string, body?: unknown): Promise<T> {
  for (const [m, pattern, handler] of ROUTES) {
    const params = m === method ? match(pattern, path) : null;
    if (params) return structuredClone(handler(params, body)) as T;
  }
  throw new MockMissingError(`no mock for ${method} ${path}`);
}

export type { MockHandler, MockRoute } from "./types";
export { replay, type ReplayFrame } from "./ws-replay";
