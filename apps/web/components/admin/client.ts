"use client";

// 관리자 화면 공용: 토큰 보관, API 호출 묶음, 오류 문구, 로딩 훅.
import { useCallback, useEffect, useRef, useState, useSyncExternalStore } from "react";

import { api } from "@/lib/api";

import type { Adjustment, Candidate, Catalog, InviteResult, Position, Report } from "./types";

const TOKEN_KEY = "dayzero.admin.token";
const TOKEN_EVENT = "dayzero-admin-token";

function readToken(): string | null {
  try {
    return window.localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

export function setToken(token: string | null) {
  try {
    if (token) window.localStorage.setItem(TOKEN_KEY, token);
    else window.localStorage.removeItem(TOKEN_KEY);
  } catch {
    // 저장소를 못 쓰면 이번 방문 동안만 메모리에 두는 대신 로그인 화면으로 돌아온다
  }
  window.dispatchEvent(new Event(TOKEN_EVENT));
}

function subscribe(onChange: () => void) {
  window.addEventListener(TOKEN_EVENT, onChange);
  window.addEventListener("storage", onChange);
  return () => {
    window.removeEventListener(TOKEN_EVENT, onChange);
    window.removeEventListener("storage", onChange);
  };
}

/** 서버 렌더에서는 null. 로그인 여부는 클라이언트에서만 안다. */
export function useToken(): string | null {
  return useSyncExternalStore(subscribe, readToken, () => null);
}

const ERROR_TEXT: Record<string, string> = {
  conflict: "이미 사용 중이거나 지금 상태에서는 할 수 없는 요청입니다.",
  unauthorized: "이메일 또는 비밀번호가 맞지 않습니다.",
  invalid_elements: "평가 요소는 1개 이상 4개 이하로 중복 없이 골라 주세요.",
  memo_required: "값을 바꾼 항목에는 메모를 적어야 합니다.",
  invalid_item: "이 채용 건의 평가표에 없는 항목입니다.",
  duplicate_item: "같은 항목이 두 번 들어 있습니다.",
  already_reviewed:
    "이미 다른 내용으로 검토가 제출되었습니다. 화면을 새로 고쳐 확정된 값을 확인하세요.",
};

/** ApiError와 mock 오류 모두 code를 가지므로 모양으로 읽는다. */
export function errorCode(error: unknown): string | null {
  const code = (error as { code?: unknown } | null)?.code;
  return typeof code === "string" ? code : null;
}

export function errorMessage(error: unknown): string {
  const code = errorCode(error);
  if (code && ERROR_TEXT[code]) return ERROR_TEXT[code];
  return error instanceof Error ? error.message : "요청을 처리하지 못했습니다.";
}

export const adminApi = {
  signup: (body: { email: string; password: string; company_name: string }) =>
    api<{ token: string }>("/admin/auth/signup", { method: "POST", body }),
  login: (body: { email: string; password: string }) =>
    api<{ token: string }>("/admin/auth/login", { method: "POST", body }),
  catalog: (token: string) => api<Catalog>("/admin/catalog", { token }),
  positions: (token: string) => api<Position[]>("/admin/positions", { token }),
  createPosition: (token: string, body: { name: string; elements: string[] }) =>
    api<{ id: string; name: string; elements: string[] }>("/admin/positions", {
      method: "POST",
      token,
      body,
    }),
  candidates: (token: string, positionId: string) =>
    api<Candidate[]>(`/admin/positions/${positionId}/candidates`, { token }),
  invite: (
    token: string,
    positionId: string,
    body: { alias: string; email: string; previous_session_id?: string },
  ) => api<InviteResult>(`/admin/positions/${positionId}/invites`, { method: "POST", token, body }),
  cancel: (token: string, sessionId: string) =>
    api<{ status: string }>(`/admin/sessions/${sessionId}/cancel`, { method: "POST", token }),
  report: (token: string, sessionId: string) =>
    api<Report>(`/admin/sessions/${sessionId}/report`, { token }),
  review: (token: string, sessionId: string, body: { adjustments: Adjustment[]; memo?: string }) =>
    api<{ status: string }>(`/admin/sessions/${sessionId}/review`, {
      method: "POST",
      token,
      body,
    }),
};

export type Loaded<T> = {
  data: T | null;
  error: string | null;
  /** 연속 실패 횟수(성공하면 0) */
  failures: number;
  reload: () => void;
};

/**
 * 로그인한 뒤 마운트 때와 key가 바뀌거나 reload()를 부를 때 load(token)을 부른다.
 * 조회가 실패해도 마지막 성공 데이터는 유지한다(폴링 중 일시 오류로 화면이 비지 않게).
 */
export function useLoad<T>(load: (token: string) => Promise<T>, key = ""): Loaded<T> {
  const token = useToken();
  const loadRef = useRef(load);
  const [state, setState] = useState<{ data: T | null; error: string | null; failures: number }>({
    data: null,
    error: null,
    failures: 0,
  });
  const [tick, setTick] = useState(0);

  useEffect(() => {
    loadRef.current = load;
  });

  useEffect(() => {
    if (!token) return;
    let live = true;
    loadRef.current(token).then(
      (data) => live && setState({ data, error: null, failures: 0 }),
      (error) =>
        live &&
        setState((prev) => ({
          data: prev.data,
          error: errorMessage(error),
          failures: prev.failures + 1,
        })),
    );
    return () => {
      live = false;
    };
  }, [token, key, tick]);

  const reload = useCallback(() => setTick((n) => n + 1), []);
  return { ...state, reload };
}
