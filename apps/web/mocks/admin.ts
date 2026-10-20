// 관리자 화면 mock 경로(web-admin 트랙 소유). fixture는 fixtures/admin/에 둔다.
// 서버 규칙(오류 코드·우선순위)은 services/api/app/routers/admin.py를 따르고, 상태는 모듈 안에만 둔다.
import type {
  Adjustment,
  Candidate,
  Catalog,
  ItemValue,
  Position,
  Report,
  Tally,
} from "@/components/admin/types";

import candidatesFixture from "./fixtures/admin/candidates.json";
import catalogFixture from "./fixtures/admin/catalog.json";
import positionsFixture from "./fixtures/admin/positions.json";
import reportFixture from "./fixtures/admin/report.json";
import type { MockRoute } from "./types";

class MockApiError extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
    message: string,
  ) {
    super(message);
  }
}

const catalog = catalogFixture as unknown as Catalog;

// 확정 중 폴링이 reviewed로 바뀌기까지 GET 횟수
const POLLS_UNTIL_FINAL = 2;

type ReportState = {
  report: Report;
  phase: "draft" | "approving" | "final";
  polls: number;
  submitted: string | null;
};

type Store = {
  positions: Position[];
  candidates: Record<string, Candidate[]>;
  reports: Record<string, ReportState>;
  counter: number;
};

let store: Store = fresh();

function fresh(): Store {
  return {
    positions: structuredClone(positionsFixture) as Position[],
    candidates: {
      "pos-1": structuredClone(candidatesFixture) as Candidate[],
      "pos-2": [],
    },
    reports: {},
    counter: 0,
  };
}

/** 테스트용: 처음 상태로 되돌린다. */
export function resetAdminMock() {
  store = fresh();
}

function findCandidate(sessionId: string): Candidate | null {
  for (const rows of Object.values(store.candidates)) {
    const row = rows.find((c) => c.session_id === sessionId);
    if (row) return row;
  }
  return null;
}

function tally(values: ItemValue[]): Tally {
  return {
    met: values.filter((v) => v === 1).length,
    judged: values.filter((v) => v !== null).length,
    no_record: values.filter((v) => v === null).length,
  };
}

function normalize(adjustments: Adjustment[], memo: string | undefined) {
  const rows = adjustments.map((a) => ({ ...a, memo: a.memo.trim() }));
  rows.sort((a, b) => a.item_id.localeCompare(b.item_id));
  return JSON.stringify({ rows, memo: (memo ?? "").trim() });
}

type ReviewBody = { adjustments?: Adjustment[]; memo?: string };

/** 서버와 같은 검증: invalid_item, duplicate_item, memo_required(자동 값과 다를 때). 바뀐 항목만 돌려준다. */
function validate(report: Report, body: ReviewBody): Adjustment[] {
  const items = new Map(report.rubric.elements.flatMap((e) => e.items.map((i) => [i.id, i])));
  const seen = new Set<string>();
  const changes: Adjustment[] = [];
  for (const adjustment of body.adjustments ?? []) {
    const item = items.get(adjustment.item_id);
    if (!item) throw new MockApiError(400, "invalid_item", `unknown item: ${adjustment.item_id}`);
    if (seen.has(adjustment.item_id))
      throw new MockApiError(400, "duplicate_item", `duplicate item: ${adjustment.item_id}`);
    seen.add(adjustment.item_id);
    if (adjustment.value === item.auto) continue;
    if (!adjustment.memo?.trim())
      throw new MockApiError(400, "memo_required", `memo required: ${adjustment.item_id}`);
    changes.push({ ...adjustment, memo: adjustment.memo.trim() });
  }
  return changes;
}

function applyReview(state: ReportState, body: ReviewBody, changes: Adjustment[]) {
  const { report } = state;
  const byItem = new Map(changes.map((c) => [c.item_id, c]));
  const now = new Date().toISOString();
  const all: ItemValue[] = [];
  const history: Report["rubric"]["history"] = [];
  for (const element of report.rubric.elements) {
    const values: ItemValue[] = [];
    for (const item of element.items) {
      const change = byItem.get(item.id);
      item.reviewer = change ? change.value : null;
      item.memo = change ? change.memo : null;
      item.adjusted = !!change;
      values.push(change ? change.value : item.auto);
      if (change) {
        history.push({
          item_id: item.id,
          element: element.element,
          auto: item.auto,
          reviewer: change.value,
          memo: change.memo,
          created_at: now,
        });
      }
    }
    element.reviewer = tally(values);
    all.push(...values);
  }
  report.rubric.reviewer_total = tally(all);
  report.rubric.review = { memo: body.memo?.trim() || null, reviewed_at: null };
  report.rubric.history = history;
  state.phase = "approving";
  state.submitted = normalize(changes, body.memo);

  const row = findCandidate(report.session_id);
  if (row) {
    row.status = row.display_status = "approving";
    row.score = {
      ...report.rubric.reviewer_total,
      source: "reviewer",
      by_element: report.rubric.elements.map((e) => ({
        element: e.element,
        met: e.reviewer!.met,
        judged: e.reviewer!.judged,
      })),
    };
  }
}

function finalize(state: ReportState) {
  const now = new Date().toISOString();
  state.phase = "final";
  state.report.stage = "final";
  state.report.reviewed_at = now;
  if (state.report.rubric.review) state.report.rubric.review.reviewed_at = now;
  const row = findCandidate(state.report.session_id);
  if (row) row.status = row.display_status = "reviewed";
}

// 목록 픽스처에서 approving·reviewed로 시작하는 세션의 사전 조정(점수 칩과 맞춘다)
const SEEDED: Record<string, Adjustment[]> = {
  "s-approving": [
    {
      item_id: "coop_replied_within_5m",
      value: 1,
      memo: "요청 확인 뒤 바로 답을 썼고 표시 시각만 늦었음",
    },
    { item_id: "coop_specific_response", value: 0, memo: "구체적인 방식 없이 인사만 있었음" },
  ],
  "s-reviewed": [
    {
      item_id: "resp_opened_after_release",
      value: 1,
      memo: "열람 기록은 없지만 인터뷰 내용을 정확히 인용함",
    },
    ...[
      "coop_replied",
      "coop_replied_within_5m",
      "coop_offered_help",
      "coop_specific_response",
    ].map((item_id) => ({ item_id, value: null, memo: "협력 상황은 이번 세션에서 판단하지 않음" })),
  ],
};

function reportState(sessionId: string): ReportState {
  const cached = store.reports[sessionId];
  if (cached) return cached;
  const row = findCandidate(sessionId);
  if (!row?.score) throw new MockApiError(404, "not_found", "report not ready");
  const report = structuredClone(reportFixture) as unknown as Report;
  report.session_id = sessionId;
  report.alias = row.alias;
  const state: ReportState = { report, phase: "draft", polls: 0, submitted: null };
  const seeded = SEEDED[sessionId];
  if (seeded) {
    // applyReview가 목록 행을 approving으로 바꾸므로 처음 상태를 먼저 적어 둔다
    const wasReviewed = row.status === "reviewed";
    applyReview(state, { memo: "자동 기록과 면담 내용을 대조해 조정함" }, seeded);
    if (wasReviewed) finalize(state);
    else row.status = row.display_status = "approving";
  }
  store.reports[sessionId] = state;
  return state;
}

function getReport(params: Record<string, string>) {
  const state = reportState(params.id);
  if (state.phase === "approving") {
    state.polls += 1;
    if (state.polls >= POLLS_UNTIL_FINAL) finalize(state);
  }
  return state.report;
}

function postReview(params: Record<string, string>, raw: unknown) {
  const body = (raw ?? {}) as ReviewBody;
  const state = reportState(params.id);
  if (state.phase !== "draft") {
    // 이미 제출된 세션은 본문 검증(400)보다 already_reviewed(409)가 먼저다
    let key: string | null = null;
    try {
      key = normalize(validate(state.report, body), body.memo);
    } catch {
      key = null;
    }
    if (key !== null && key === state.submitted)
      return { status: state.phase === "final" ? "reviewed" : "approving" };
    throw new MockApiError(
      409,
      "already_reviewed",
      "review already submitted with different content",
    );
  }
  applyReview(state, body, validate(state.report, body));
  return { status: "approving" };
}

function createPosition(_: Record<string, string>, raw: unknown) {
  const body = (raw ?? {}) as { name?: string; elements?: string[] };
  const elements = body.elements ?? [];
  const known = new Set(catalog.elements.map((e) => e.id));
  if (
    elements.length < 1 ||
    elements.length > 4 ||
    new Set(elements).size !== elements.length ||
    elements.some((id) => !known.has(id))
  ) {
    throw new MockApiError(400, "invalid_elements", "elements must be 1-4 unique catalog ids");
  }
  if (!body.name?.trim()) throw new MockApiError(422, "invalid_input", "name is required");
  store.counter += 1;
  const id = `pos-new-${store.counter}`;
  store.positions.push({
    id,
    name: body.name.trim(),
    elements,
    candidate_count: 0,
    created_at: new Date().toISOString(),
  });
  store.candidates[id] = [];
  return { id, name: body.name.trim(), elements, scenario: {}, catalog_version: "mock" };
}

function createInvite(params: Record<string, string>, raw: unknown) {
  const body = (raw ?? {}) as { alias?: string; email?: string; previous_session_id?: string };
  const position = store.positions.find((p) => p.id === params.id);
  if (!position) throw new MockApiError(404, "not_found", "position not found");
  if (!body.alias?.trim() || !body.email?.trim())
    throw new MockApiError(422, "invalid_input", "alias and email are required");
  store.counter += 1;
  const sessionId = `s-new-${store.counter}`;
  const now = new Date();
  const expires = new Date(now.getTime() + 72 * 3600 * 1000);
  store.candidates[position.id].push({
    session_id: sessionId,
    alias: body.alias.trim(),
    status: "invited",
    display_status: "invited",
    invited_at: now.toISOString(),
    report_ready_at: null,
    score: null,
    ...(body.previous_session_id && { previous_session_id: body.previous_session_id }),
  });
  position.candidate_count += 1;
  const inviteUrl = `http://localhost:3000/s/mock-invite-${store.counter}`;
  return {
    session_id: sessionId,
    invite_url: inviteUrl,
    expires_at: expires.toISOString(),
    notice_text: catalog.candidate_notice_template
      .replace("{alias}", body.alias.trim())
      .replace("{virtual_company}", "루프랩")
      .replace("{expires_at}", expires.toISOString().slice(0, 16).replace("T", " ") + " UTC")
      .replace("{invite_url}", inviteUrl),
  };
}

function cancel(params: Record<string, string>) {
  const row = findCandidate(params.id);
  if (!row) throw new MockApiError(404, "not_found", "session not found");
  if (row.status !== "invited") throw new MockApiError(409, "conflict", "only invited can cancel");
  row.status = row.display_status = "cancelled";
  return { status: "cancelled" };
}

export const ROUTES: MockRoute[] = [
  [
    "POST",
    "/admin/auth/signup",
    (_, body) => {
      if ((body as { email?: string })?.email === "taken@example.com")
        throw new MockApiError(409, "conflict", "email already registered");
      return { token: "mock-admin-token" };
    },
  ],
  [
    "POST",
    "/admin/auth/login",
    (_, body) => {
      if ((body as { password?: string })?.password === "wrong")
        throw new MockApiError(401, "unauthorized", "invalid email or password");
      return { token: "mock-admin-token" };
    },
  ],
  ["GET", "/admin/catalog", () => catalog],
  ["GET", "/admin/positions", () => store.positions],
  ["POST", "/admin/positions", createPosition],
  ["GET", "/admin/positions/:id/candidates", (p) => store.candidates[p.id] ?? []],
  ["POST", "/admin/positions/:id/invites", createInvite],
  ["POST", "/admin/sessions/:id/cancel", cancel],
  ["GET", "/admin/sessions/:id/report", getReport],
  ["POST", "/admin/sessions/:id/review", postReview],
];
