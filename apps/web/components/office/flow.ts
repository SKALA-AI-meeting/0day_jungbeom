// 지원자 흐름: 링크 입장 → 안내·동의 → 대기 → 오피스 → 보고 대기 → 디브리핑. 단계 판정과 api 호출을 모은다.
// 화면은 이 함수들만 부르고, 계약 경로(docs/common/contracts.md 지원자 REST)는 이 파일에만 둔다.
import { api } from "@/lib/api";

import type {
  Assignee,
  AssistantReply,
  CompanyDoc,
  Debrief,
  Entry,
  FinalSection,
  OpenedDocument,
  StateSnapshot,
  Task,
} from "./types";

/** 링크로 들어왔을 때 보여 줄 첫 화면 */
export type Landing =
  | { kind: "entry"; entry: Entry }
  | { kind: "resume"; entry: Entry }
  | { kind: "ended"; entry: Entry }
  | { kind: "notice"; title: string; description: string; retry?: boolean };

export const LINK_NOTICES = {
  expired: {
    title: "링크가 만료되었습니다",
    description: "초대 링크는 72시간 동안 열립니다. 채용 담당자에게 새 링크를 요청해 주세요.",
  },
  cancelled: {
    title: "취소된 초대입니다",
    description: "채용 담당자가 이 초대를 취소했습니다. 궁금한 점은 담당자에게 문의해 주세요.",
  },
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

export function errorText(error: unknown): string | undefined {
  return error instanceof Error ? error.message : undefined;
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
  if (entry.status === "in_progress" || entry.status === "reporting") {
    return { kind: "resume", entry };
  }
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
const doc = (id: string) => encodeURIComponent(id);

export type TaskPatch = Partial<Pick<Task, "status" | "order" | "due_min">> & {
  assignee?: Assignee | null;
};

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
  saveDoc: (id: string, jwt: string, partNo: number, content: string) =>
    api<{ updated_at: string; revision: number }>(`/sessions/${id}/my-documents/${partNo}`, {
      method: "PUT",
      token: jwt,
      body: { content },
    }),
  saveFinal: (id: string, jwt: string, sections: { part_no: number; content: string }[]) =>
    api<{ updated_at: string; revision: number }>(`/sessions/${id}/my-documents/final`, {
      method: "PUT",
      token: jwt,
      body: { sections },
    }),
  /** note: 문서 카드에 함께 보낼 한마디(선택). 비우면 카드만 올라간다 */
  share: (id: string, jwt: string, partNo: number, channel: "team" | "dm", note?: string) =>
    api<{ version: number; message_id: string }>(`/sessions/${id}/my-documents/${partNo}/share`, {
      method: "POST",
      token: jwt,
      body: note?.trim() ? { channel, note: note.trim() } : { channel },
    }),
  open: (id: string, jwt: string, docId: string, version: number) =>
    api<OpenedDocument>(`/sessions/${id}/documents/${doc(docId)}/open`, {
      method: "POST",
      token: jwt,
      body: { version },
    }),
  importSection: (
    id: string,
    jwt: string,
    partNo: number,
    /** version null = 보내지 않은 내 문서의 현재 저장본 */
    source: { source_doc_id: string; version: number | null },
  ) =>
    api<FinalSection>(`/sessions/${id}/final/sections/${partNo}/import`, {
      method: "PUT",
      token: jwt,
      body: source,
    }),
  putTask: (id: string, jwt: string, partNo: number, patch: TaskPatch) =>
    api<Task>(`/sessions/${id}/tasks/${partNo}`, { method: "PUT", token: jwt, body: patch }),
  documents: (id: string, jwt: string) =>
    api<CompanyDoc[]>(`/sessions/${id}/documents`, { token: jwt }),
  document: (id: string, jwt: string, docId: string) =>
    api<{ doc_id: string; title: string; content: string }>(
      `/sessions/${id}/documents/${doc(docId)}`,
      { token: jwt },
    ),
  assistant: (id: string, jwt: string, prompt: string) =>
    api<AssistantReply>(`/sessions/${id}/assistant`, {
      method: "POST",
      token: jwt,
      body: { prompt },
    }),
  submit: (id: string, jwt: string) =>
    api<{ status: string; deadline_at?: string | null }>(`/sessions/${id}/submit`, {
      method: "POST",
      token: jwt,
    }),
  debrief: (id: string, jwt: string) => api<Debrief>(`/sessions/${id}/debrief`, { token: jwt }),
  survey: (id: string, jwt: string, answers: { q: string; value: number }[]) =>
    api<{ submitted: boolean }>(`/sessions/${id}/debrief/survey`, {
      method: "POST",
      token: jwt,
      body: { answers },
    }),
};

export type CandidateApi = typeof candidateApi;

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
