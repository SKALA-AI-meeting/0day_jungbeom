// api 호출 래퍼. 계약은 docs/common/contracts.md. 오류는 {"error": {code, message}} → ApiError.
// NEXT_PUBLIC_MOCK=1이면 네트워크 대신 mocks/의 계약 예시 응답을 돌려준다.
import { mockRequest } from "@/mocks";

export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
export const WS_URL = process.env.NEXT_PUBLIC_WS_URL ?? "ws://localhost:8000";
export const MOCK = process.env.NEXT_PUBLIC_MOCK === "1";

export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

export type HttpMethod = "GET" | "POST" | "PUT";

export type RequestOptions = {
  method?: HttpMethod;
  body?: unknown;
  /** Authorization: Bearer <token> (관리자 JWT 또는 세션 JWT) */
  token?: string | null;
  /** 변경 요청 멱등 키(선택) */
  idempotencyKey?: string;
  signal?: AbortSignal;
};

export async function api<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const method = options.method ?? "GET";
  if (MOCK) {
    try {
      return await mockRequest<T>(method, path, options.body);
    } catch (error) {
      // mock 서버의 오류({status, code})도 실제 응답과 같은 ApiError로 바꾼다
      const e = error as { status?: number; code?: string; message?: string };
      if (typeof e.status === "number")
        throw new ApiError(e.status, e.code ?? "http_error", e.message ?? "");
      throw error;
    }
  }

  const headers: Record<string, string> = { Accept: "application/json" };
  if (options.body !== undefined) headers["Content-Type"] = "application/json";
  if (options.token) headers.Authorization = `Bearer ${options.token}`;
  if (options.idempotencyKey) headers["Idempotency-Key"] = options.idempotencyKey;

  const response = await fetch(`${API_URL}${path}`, {
    method,
    headers,
    body: options.body === undefined ? undefined : JSON.stringify(options.body),
    signal: options.signal,
  });
  const data = response.status === 204 ? null : await response.json().catch(() => null);
  if (!response.ok) {
    const error = data?.error ?? {};
    throw new ApiError(
      response.status,
      error.code ?? "http_error",
      error.message ?? response.statusText,
    );
  }
  return data as T;
}

/** 계약의 /assets/... 경로(avatar_url)는 api 서버가 서빙한다. 웹 출처와 다르니 api 주소를 붙인다 */
export const assetUrl = (url: string) => (url.startsWith("/assets/") ? `${API_URL}${url}` : url);

/** WS 주소: /ws/sessions/{id}?token=<세션 JWT> */
export function sessionSocketUrl(sessionId: string, token: string) {
  return `${WS_URL}/ws/sessions/${sessionId}?token=${encodeURIComponent(token)}`;
}
