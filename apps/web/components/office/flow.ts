// 지원자 흐름: 링크 입장 → 안내·동의 → 대기 → 오피스 → 디브리핑. 단계 판정과 api 호출을 모은다.
// 화면은 이 함수들만 부르고, 계약 경로는 이 파일에만 둔다.
import { api } from "@/lib/api";

import type { OfficeAction } from "./reducer";
import type {
  AssistantReply,
  CompanyDoc,
  Debrief,
  Entry,
  StateSnapshot,
  Task,
  TaskStatus,
} from "./types";

/** 링크로 들어왔을 때 보여 줄 첫 화면 */
export type Landing =
  | { kind: "entry"; entry: Entry }
  | { kind: "resume"; entry: Entry }
  | { kind: "ended"; entry: Entry }
  | { kind: "notice"; title: string; description: string; retry?: boolean };

export const LINK_NOTICES = {
  expired: { title: "링크가 만료되었습니다", description: "채용 담당자에게 문의해 주세요." },
  cancelled: { title: "취소된 초대입니다", description: "채용 담당자에게 문의해 주세요." },
  not_found: {
    title: "초대 링크를 찾을 수 없습니다",
    description: "받은 주소를 다시 확인해 주세요.",
  },
  unknown: {
    title: "잠시 연결할 수 없습니다",
    description: "네트워크 상태를 확인하고 다시 시도해 주세요. 진행 중인 과제는 그대로 이어집니다.",
  },
  debrief_expired: {
    title: "안내를 볼 수 있는 기한이 지났습니다",
    description: "과제 종료 후 7일이 지났습니다. 채용 담당자에게 문의해 주세요.",
  },
  submitted: {
    title: "제출되었습니다",
    description: "수고하셨습니다. 안내는 잠시 후 이 링크에서 다시 볼 수 있어요.",
  },
} as const;

/** ApiError(lib/api)와 mock 오류 모두 {status, code}를 가진다. */
export function errorCode(error: unknown): string | undefined {
  return typeof error === "object" && error && "code" in error ? String(error.code) : undefined;
}

export function landingFromError(error: unknown): Extract<Landing, { kind: "notice" }> {
  const code = errorCode(error);
  const notice =
    code === "expired" || code === "cancelled" || code === "not_found"
      ? LINK_NOTICES[code]
      : LINK_NOTICES.unknown;
  return { kind: "notice", ...notice, retry: notice === LINK_NOTICES.unknown };
}

export function landingFromEntry(entry: Entry): Landing {
  if (entry.status === "invited") return { kind: "entry", entry };
  if (entry.status === "in_progress") return { kind: "resume", entry };
  return { kind: "ended", entry };
}

export async function land(token: string): Promise<Landing> {
  try {
    return landingFromEntry(await api<Entry>(`/s/${encodeURIComponent(token)}`));
  } catch (error) {
    return landingFromError(error);
  }
}

/** 세션 JWT·디브리핑 JWT의 sub가 session_id다(GET /s/{token}은 id를 주지 않는다). */
export function sessionIdFromToken(jwt: string): string {
  const payload = jwt.split(".")[1] ?? "";
  const base64 = payload.replace(/-/g, "+").replace(/_/g, "/");
  const json = new TextDecoder().decode(Uint8Array.from(atob(base64), (c) => c.charCodeAt(0)));
  return JSON.parse(json).sub;
}

const link = (token: string) => `/s/${encodeURIComponent(token)}`;

export const candidateApi = {
  consent: (token: string) =>
    api<{ session_token: string }>(`${link(token)}/consent`, { method: "POST" }),
  resume: (token: string) =>
    api<{ session_token: string }>(`${link(token)}/resume`, { method: "POST" }),
  start: (token: string, jwt: string) =>
    api<{ session_id: string; started_at: string; ends_at: string }>(`${link(token)}/start`, {
      method: "POST",
      token: jwt,
    }),
  state: (id: string, jwt: string) => api<StateSnapshot>(`/sessions/${id}/state`, { token: jwt }),
  putPart: (id: string, jwt: string, partNo: number, content: string) =>
    api<{ updated_at: string; revision: number }>(`/sessions/${id}/document/${partNo}`, {
      method: "PUT",
      token: jwt,
      body: { content },
    }),
  putTask: (id: string, jwt: string, partNo: number, status: TaskStatus) =>
    api<Task>(`/sessions/${id}/tasks/${partNo}`, { method: "PUT", token: jwt, body: { status } }),
  documents: (id: string, jwt: string) =>
    api<CompanyDoc[]>(`/sessions/${id}/documents`, { token: jwt }),
  document: (id: string, jwt: string, docId: string) =>
    api<{ doc_id: string; title: string; content: string }>(
      `/sessions/${id}/documents/${encodeURIComponent(docId)}`,
      { token: jwt },
    ),
  assistant: (id: string, jwt: string, prompt: string) =>
    api<AssistantReply>(`/sessions/${id}/assistant`, {
      method: "POST",
      token: jwt,
      body: { prompt },
    }),
  submit: (id: string, jwt: string) =>
    api<{ status: "completed" }>(`/sessions/${id}/submit`, { method: "POST", token: jwt }),
  debrief: (id: string, jwt: string) => api<Debrief>(`/sessions/${id}/debrief`, { token: jwt }),
};

export type CandidateApi = typeof candidateApi;

/**
 * 제출: 대기 중인 문서 저장을 먼저 끝내고 submit을 부른다(contracts.md).
 * 저장이 실패하면 submit을 부르지 않고 거부한다(원고 보존). submit이 session_ending·conflict면
 * 이미 끝났을 수 있으므로 isEnded(/state)로 실제 종료를 확인한 뒤에만 끝난 것으로 본다.
 */
export async function submitSession(
  flush: () => Promise<void>,
  submit: () => Promise<unknown>,
  isEnded: () => Promise<boolean>,
): Promise<"submitted" | "ended"> {
  await flush();
  try {
    await submit();
    return "submitted";
  } catch (error) {
    const code = errorCode(error);
    if ((code === "session_ending" || code === "conflict") && (await isEnded())) return "ended";
    throw error;
  }
}

export const STATE_RETRY_MS = 3000;

/** /state를 받을 때까지 다시 시도한다. alive가 false가 되면(연결이 바뀜·화면 닫힘) null. */
export async function fetchSnapshot(
  load: () => Promise<StateSnapshot>,
  alive: () => boolean,
  delay = STATE_RETRY_MS,
): Promise<StateSnapshot | null> {
  while (alive()) {
    try {
      return await load();
    } catch {
      await new Promise((resolve) => setTimeout(resolve, delay));
    }
  }
  return null;
}

/**
 * 기획안 파트 저장 콜백(PartSaver의 save). 성공이면 saved, 동료 담당(403 forbidden)이면
 * 남은 저장을 버리고 서버 본문으로 되돌린 뒤 정상 반환, 그 밖의 실패는 save_failed 후 다시 던진다.
 */
export function partSaveHandler(deps: {
  put: (partNo: number, content: string) => Promise<{ revision: number }>;
  refresh: () => Promise<StateSnapshot | null>;
  dispatch: (action: OfficeAction) => void;
  cancel: (partNo: number) => void;
}) {
  return async (partNo: number, content: string) => {
    try {
      const saved = await deps.put(partNo, content);
      deps.dispatch({ type: "saved", part_no: partNo, content, revision: saved.revision });
    } catch (error) {
      if (errorCode(error) !== "forbidden") {
        deps.dispatch({ type: "save_failed", part_no: partNo });
        throw error;
      }
      deps.cancel(partNo);
      deps.dispatch({ type: "rejected", part_no: partNo });
      const snapshot = await deps.refresh().catch(() => null);
      if (snapshot) deps.dispatch({ type: "snapshot", state: snapshot, now: Date.now() });
    }
  };
}

/** 세션 JWT를 탭 단위로 기억한다. 없어도 링크만으로 /resume이 가능하므로 실패는 무시한다. */
export const tokenStore = {
  get(token: string): string | null {
    try {
      return sessionStorage.getItem(`dz:${token}`);
    } catch {
      return null;
    }
  },
  set(token: string, jwt: string) {
    try {
      sessionStorage.setItem(`dz:${token}`, jwt);
    } catch {
      // 저장소를 못 쓰는 환경이면 메모리 값만 쓴다
    }
  },
};
