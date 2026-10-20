// 관리자 화면 mock 서버. 오류 코드와 우선순위는 docs/common/contracts.md "관리자 REST"를 따르고 상태는 모듈 안에만 둔다.
//
// 데이터: 채용 건 pos-1(admin_positions.json), 지원자 sess-1~3(admin_candidates.json) + 묶음 5종을 채우는
// sess-4~8(admin_candidates_extra.json). 리포트는 sess-1(draft, report.json)과 sess-6(final, report.json에 검토를 더함).
// 검토자 이름에 "지연"을 넣으면 확정이 끝나지 않아 "확정만 다시 시도" 화면을 볼 수 있다(다시 제출하면 끝난다).
import type {
  Adjustment,
  Candidate,
  Catalog,
  ElementId,
  Position,
  RecordEntry,
  Report,
} from "@/components/admin/types";

import candidatesFixture from "./fixtures/admin_candidates.json";
import extraCandidates from "./fixtures/admin_candidates_extra.json";
import catalogFixture from "./fixtures/admin_catalog.json";
import createdFixture from "./fixtures/admin_position_created.json";
import inviteFixture from "./fixtures/admin_invite.json";
import notesFixture from "./fixtures/admin_report_notes.json";
import positionsFixture from "./fixtures/admin_positions.json";
import recordFixture from "./fixtures/admin_record.json";
import reportFixture from "./fixtures/report.json";
import type { MockRoute } from "./types";
import { LONG_ALIAS, LONG_DOC, LONG_EMAIL, LONG_MESSAGE, LONG_POSITION, WORST } from "./worst";

class MockApiError extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
    message?: string,
  ) {
    super(message ?? code);
  }
}

const catalog = catalogFixture as unknown as Catalog;
const INVITE_HOURS = 72;
// 확정 중(approving) 리포트가 final로 바뀌기까지 GET 횟수
const POLLS_UNTIL_FINAL = 2;

type ReviewBody = { adjustments: Adjustment[]; memo?: string; reviewer_name: string };

type ReportState = {
  report: Report;
  polls: number;
  submitted: string | null;
  stuck: boolean;
};

type Store = {
  positions: Position[];
  candidates: Record<string, Candidate[]>;
  reports: Record<string, ReportState>;
  counter: number;
};

let store: Store = WORST ? worst(fresh()) : fresh();

/** 검토가 끝난 상태의 리포트(sess-6): 조정 1건·검토 메모·추가 메모 1건 */
function reviewedReport(): Report {
  const report = structuredClone(reportFixture) as unknown as Report;
  report.session_id = "sess-6";
  report.alias = "지원자E";
  report.stage = "final";
  const item = report.rubric.elements[0].cards[0].items[2];
  Object.assign(item, {
    reviewer: 1,
    memo: "62분 메시지의 '3번 골격을 지표 기준으로 먼저' 제안을 대안으로 봄",
    adjusted: true,
  });
  report.rubric.reviewer_total = { met: 17, unmet: 1, no_record: 2 };
  report.rubric.review = {
    memo: "전반적으로 자동 서술과 일치",
    reviewer_name: "김담당",
    reviewed_at: "2026-10-16T02:00:00Z",
  };
  report.reviewed_at = "2026-10-16T02:00:00Z";
  report.notes = structuredClone(notesFixture.notes);
  return report;
}

function fresh(): Store {
  return {
    positions: structuredClone(positionsFixture) as Position[],
    candidates: {
      "pos-1": [
        ...(structuredClone(candidatesFixture) as Candidate[]),
        ...(structuredClone(extraCandidates) as Candidate[]),
      ],
    },
    reports: {
      "sess-1": {
        report: structuredClone(reportFixture) as unknown as Report,
        polls: 0,
        submitted: null,
        stuck: false,
      },
      "sess-6": { report: reviewedReport(), polls: 0, submitted: null, stuck: false },
    },
    counter: 0,
  };
}

/** ?data=worst: 긴 이름·이메일, 한 글자 별칭, 긴 최종본, 지원자 없는 채용 건 */
function worst(store: Store): Store {
  store.positions[0].name = LONG_POSITION;
  store.positions.push({
    ...store.positions[0],
    id: "pos-empty",
    name: "지원자 없는 채용 건",
    candidate_count: 0,
  });
  store.candidates["pos-empty"] = [];
  const [a, b] = store.candidates["pos-1"];
  Object.assign(a, { alias: LONG_ALIAS, email: LONG_EMAIL });
  Object.assign(b, { alias: "Jo" });
  const report = store.reports["sess-1"].report;
  report.alias = LONG_ALIAS;
  report.position.name = LONG_POSITION;
  report.deliverable.final.sections[0].content = LONG_DOC;
  report.deliverable.final_report_message!.content = LONG_MESSAGE;
  return store;
}

export function resetAdminMock() {
  store = fresh();
}

function auth(body: unknown, signup: boolean) {
  const { email, password } = (body ?? {}) as { email?: string; password?: string };
  if (signup && email === "taken@example.com") {
    throw new MockApiError(409, "conflict", "이미 가입된 이메일입니다.");
  }
  if (!signup && password === "wrong") throw new MockApiError(401, "unauthorized");
  return { token: "mock-admin-token" };
}

function createPosition(body: unknown) {
  const {
    name,
    elements,
    mission_id = "planning",
  } = (body ?? {}) as {
    name?: string;
    elements?: string[];
    mission_id?: string;
  };
  const ids = new Set(catalog.elements.map((e) => e.id as string));
  if (
    !Array.isArray(elements) ||
    elements.length < 1 ||
    elements.length > ids.size ||
    new Set(elements).size !== elements.length ||
    elements.some((e) => !ids.has(e))
  ) {
    throw new MockApiError(
      422,
      "invalid_elements",
      "요소는 카탈로그의 1~5개를 중복 없이 고릅니다.",
    );
  }
  if (!catalog.missions.some((m) => m.id === mission_id)) {
    throw new MockApiError(422, "invalid_mission");
  }
  store.counter += 1;
  const id = `pos-new-${store.counter}`;
  const position: Position = {
    id,
    name: name?.trim() || "이름 없는 채용 건",
    mission_id,
    elements: elements as ElementId[],
    candidate_count: 0,
    created_at: new Date().toISOString(),
  };
  store.positions.unshift(position);
  store.candidates[id] = [];
  return { ...createdFixture, id, name: position.name, mission_id, elements };
}

function candidates(id: string) {
  const list = store.candidates[id];
  if (!list) throw new MockApiError(404, "not_found");
  return list;
}

function findSession(sessionId: string) {
  for (const [positionId, list] of Object.entries(store.candidates)) {
    const candidate = list.find((c) => c.session_id === sessionId);
    if (candidate) return { positionId, candidate };
  }
  throw new MockApiError(404, "not_found");
}

const RETRYABLE = new Set(["failed", "cancelled"]);

function invite(positionId: string, body: unknown) {
  const list = candidates(positionId);
  const { alias, email, previous_session_id } = (body ?? {}) as {
    alias?: string;
    email?: string;
    previous_session_id?: string;
  };
  const previous = previous_session_id
    ? list.find((c) => c.session_id === previous_session_id)
    : undefined;
  if (previous_session_id) {
    const allowed =
      previous &&
      ((previous.status === "failed" && previous.failed_stage === "session") ||
        previous.display_status === "expired" ||
        RETRYABLE.has(previous.status));
    if (!allowed) throw new MockApiError(422, "invalid_previous_session");
  }
  // 재초대는 같은 별칭을 이어 쓴다. 그 밖의 같은 별칭은 409
  if (!previous && list.some((c) => c.alias === alias)) {
    throw new MockApiError(409, "conflict", "같은 채용 건에 같은 별칭이 있습니다.");
  }
  store.counter += 1;
  const sessionId = `sess-new-${store.counter}`;
  const now = Date.now();
  const url = `${typeof window === "undefined" ? "http://localhost:3000" : window.location.origin}/s/demo`;
  list.push({
    session_id: sessionId,
    alias: alias ?? "",
    email: email ?? "",
    status: "invited",
    display_status: "invited",
    display_group: "waiting",
    invited_at: new Date(now).toISOString(),
    message_count: 0,
    previous_session_id: previous?.session_id ?? null,
    previous_relation: previous
      ? previous.display_status === "expired"
        ? "reissue"
        : "retry"
      : null,
    met: null,
    unmet: null,
    no_record: null,
    score_source: null,
    by_element: null,
  });
  const position = store.positions.find((p) => p.id === positionId);
  if (position && !previous) position.candidate_count += 1;
  return {
    session_id: sessionId,
    invite_url: url,
    expires_at: new Date(now + INVITE_HOURS * 3_600_000).toISOString(),
    notice_text: inviteFixture.notice_text
      .replace("지원자A", alias ?? "")
      .replace(inviteFixture.invite_url, url),
  };
}

function cancel(sessionId: string) {
  const { candidate } = findSession(sessionId);
  if (!["invited", "in_progress", "reporting"].includes(candidate.status)) {
    throw new MockApiError(409, "conflict");
  }
  Object.assign(candidate, {
    status: "cancelled",
    display_status: "cancelled",
    display_group: "problem",
  });
  return { status: "cancelled" };
}

function regenerate(sessionId: string) {
  const { candidate } = findSession(sessionId);
  if (candidate.status !== "failed" || candidate.failed_stage !== "report") {
    throw new MockApiError(409, "conflict");
  }
  Object.assign(candidate, {
    status: "completed",
    display_status: "completed",
    display_group: "in_progress",
    failed_stage: null,
    failed_reason: null,
    next_action: null,
  });
  return { status: "completed" };
}

function reportState(sessionId: string) {
  const state = store.reports[sessionId];
  if (!state) throw new MockApiError(404, "not_found");
  return state;
}

function setStatus(sessionId: string, status: string, group: Candidate["display_group"]) {
  const { candidate } = findSession(sessionId);
  Object.assign(candidate, { status, display_status: status, display_group: group });
  return candidate;
}

function getReport(sessionId: string) {
  const state = reportState(sessionId);
  const { report } = state;
  if (report.stage === "draft" && report.rubric.review && !state.stuck) {
    state.polls += 1;
    if (state.polls >= POLLS_UNTIL_FINAL) {
      report.stage = "final";
      report.reviewed_at = new Date().toISOString();
      report.rubric.review.reviewed_at = report.reviewed_at;
      const candidate = setStatus(sessionId, "reviewed", "done");
      candidate.score_source = "reviewer";
    }
  }
  return report;
}

function review(sessionId: string, body: unknown) {
  const state = reportState(sessionId);
  const { report } = state;
  const request = (body ?? {}) as ReviewBody;
  // 본문 비교(contracts 멱등)는 항목 순서와 무관하게 한다
  const text = JSON.stringify({
    adjustments: [...(request.adjustments ?? [])].sort((x, y) =>
      x.item_id.localeCompare(y.item_id),
    ),
    memo: request.memo ?? null,
    reviewer_name: request.reviewer_name?.trim(),
  });
  // 오류 우선순위: 이미 제출된 세션의 already_reviewed가 본문 검증보다 먼저다
  if (state.submitted) {
    if (state.submitted !== text) throw new MockApiError(409, "already_reviewed");
    state.stuck = false; // 같은 본문 재요청 = "확정만 다시 시도"
    return { status: report.stage === "final" ? "reviewed" : "approving" };
  }
  if (!request.reviewer_name?.trim()) throw new MockApiError(422, "invalid_input");
  const items = new Map(
    report.rubric.elements.flatMap((e) => e.cards.flatMap((c) => c.items)).map((i) => [i.id, i]),
  );
  const seen = new Set<string>();
  for (const adj of request.adjustments ?? []) {
    const item = items.get(adj.item_id);
    if (!item) throw new MockApiError(400, "invalid_item");
    if (seen.has(adj.item_id)) throw new MockApiError(400, "duplicate_item");
    seen.add(adj.item_id);
    if (adj.value !== item.auto && !adj.memo?.trim()) throw new MockApiError(400, "memo_required");
  }
  for (const adj of request.adjustments ?? []) {
    const item = items.get(adj.item_id)!;
    Object.assign(item, { reviewer: adj.value, memo: adj.memo, adjusted: true });
  }
  const final = (i: { auto: 1 | 0 | null; reviewer: 1 | 0 | null; adjusted: boolean }) =>
    i.adjusted ? i.reviewer : i.auto;
  const all = [...items.values()];
  report.rubric.reviewer_total = {
    met: all.filter((i) => final(i) === 1).length,
    unmet: all.filter((i) => final(i) === 0).length,
    no_record: all.filter((i) => final(i) === null).length,
  };
  report.rubric.review = {
    memo: request.memo ?? null,
    reviewer_name: request.reviewer_name.trim(),
    reviewed_at: null,
  };
  state.submitted = text;
  state.stuck = request.reviewer_name.includes("지연");
  setStatus(sessionId, "approving", "done");
  return { status: "approving" };
}

function addNote(sessionId: string, body: unknown) {
  const { report } = reportState(sessionId);
  if (!report.rubric.review) throw new MockApiError(409, "conflict");
  const { text, reviewer_name } = (body ?? {}) as { text?: string; reviewer_name?: string };
  if (!text?.trim() || !reviewer_name?.trim()) throw new MockApiError(422, "invalid_input");
  store.counter += 1;
  report.notes.push({
    id: `note-${store.counter}`,
    text: text.trim(),
    reviewer_name: reviewer_name.trim(),
    created_at: new Date().toISOString(),
  });
  return { notes: report.notes };
}

function record(sessionId: string) {
  reportState(sessionId);
  return recordFixture as RecordEntry[];
}

export const ROUTES: MockRoute[] = [
  ["POST", "/admin/auth/signup", (_, body) => auth(body, true)],
  ["POST", "/admin/auth/login", (_, body) => auth(body, false)],
  ["GET", "/admin/catalog", () => catalog],
  ["GET", "/admin/positions", () => store.positions],
  ["POST", "/admin/positions", (_, body) => createPosition(body)],
  ["GET", "/admin/positions/:id/candidates", ({ id }) => candidates(id)],
  ["POST", "/admin/positions/:id/invites", ({ id }, body) => invite(id, body)],
  ["POST", "/admin/sessions/:id/cancel", ({ id }) => cancel(id)],
  ["GET", "/admin/sessions/:id/report", ({ id }) => getReport(id)],
  ["POST", "/admin/sessions/:id/report/regenerate", ({ id }) => regenerate(id)],
  ["POST", "/admin/sessions/:id/review", ({ id }, body) => review(id, body)],
  ["POST", "/admin/sessions/:id/report/notes", ({ id }, body) => addNote(id, body)],
  ["GET", "/admin/sessions/:id/record", ({ id }) => record(id)],
];
