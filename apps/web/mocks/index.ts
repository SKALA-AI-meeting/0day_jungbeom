// NEXT_PUBLIC_MOCK=1일 때 lib/api.ts가 부르는 mock 라우터.
// 경로 표는 화면 트랙이 각자 소유한 admin.ts(mock-admin, /admin/*)·debate.ts(mock-candidate, 지원자 경로)에 있다.
// 표는 경로 앞부분으로 골라 필요할 때 불러온다: 한쪽 표가 깨져도 다른 쪽 화면은 돈다. 없는 경로는 404 오류로 알린다.
import type { MockRoute } from "./types";

async function routesFor(path: string): Promise<MockRoute[]> {
  if (path.startsWith("/admin")) return (await import("./admin")).ROUTES;
  return (await import("./debate")).ROUTES;
}

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
  for (const [m, pattern, handler] of await routesFor(path)) {
    const params = m === method ? match(pattern, path) : null;
    if (params) return structuredClone(handler(params, body)) as T;
  }
  throw new MockMissingError(`no mock for ${method} ${path}`);
}

export type { MockHandler, MockRoute } from "./types";
export { replay, type ReplayFrame } from "./ws-replay";
