// 실 API 연결 스크립트(web-integrate). 띄워 둔 api(8000·8001)·web(3000)·worker에 브라우저로 한 세션을 돌린다.
// 관리자 가입·로그인·채용 건·초대 → 6분 테스트 세션으로 지원자 전체 흐름 → 관리자 리포트·전체 기록.
// 재연결 3종(끊김 3초 재접속, 4401 → resume, session.replaced 4000)은 브라우저의 WS 경로를 가로채 닫는다.
// 동료 문서 보내기·보고 분류는 FakeAgentRunner가 하지 않으므로 내부 API로 그래프 역할을 대신한다.
// 단계별 스크린샷과 응답 로그는 e2e/shots/<실행 시각>/에 남긴다(git 무시).
//
//   node e2e/session.mjs            (환경변수: WEB_URL, API_URL, API_INTERNAL_URL, E2E_DB, HEADED=1)
import { execFileSync } from "node:child_process";
import { randomUUID } from "node:crypto";
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { chromium } from "playwright-core";

const HERE = dirname(fileURLToPath(import.meta.url));
const REPO = join(HERE, "..", "..", "..");
const WEB = process.env.WEB_URL ?? "http://localhost:3000";
const API = process.env.API_URL ?? "http://localhost:8000";
const INTERNAL = process.env.API_INTERNAL_URL ?? "http://localhost:8001";
// 테스트 세션의 채용 건을 관리자 회사로 옮길 DB(테스트 API가 고정 회사에 만든다)
const DB = process.env.E2E_DB ?? "dayzero_web_integrate";
const ELEMENTS = ["responsibility", "planning", "adaptability", "collaboration", "honesty"];

const RUN = new Date().toISOString().replace(/[:.]/g, "-");
const OUT = join(HERE, "shots", RUN);
mkdirSync(OUT, { recursive: true });

/** 내부 토큰은 env 또는 infra/.env.local에서 읽고 출력하지 않는다 */
function internalToken() {
  if (process.env.INTERNAL_TOKEN) return process.env.INTERNAL_TOKEN;
  const text = readFileSync(join(REPO, "infra", ".env.local"), "utf8");
  return /^INTERNAL_TOKEN=(.*)$/m.exec(text)?.[1]?.trim() ?? "change-me-internal";
}
const INTERNAL_TOKEN = internalToken();

// ── 기록 ─────────────────────────────────────────────────────
const log = { run: RUN, steps: [], responses: [], frames: [], checks: [], shapes: [] };
/** 경로 모양별 첫 성공 응답 본문(픽스처 모양 비교용) */
const firstBodies = new Map();
let stepNo = 0;
const t0 = Date.now();
const elapsed = () => `${((Date.now() - t0) / 1000).toFixed(1)}s`;

function save() {
  writeFileSync(join(OUT, "log.json"), JSON.stringify(log, null, 2));
}

async function shot(page, name) {
  const file = `${String(stepNo).padStart(2, "0")}-${name}.png`;
  await page.screenshot({ path: join(OUT, file), fullPage: false });
  return file;
}

async function step(name, fn) {
  stepNo += 1;
  const started = Date.now();
  console.log(`\n[${elapsed()}] ${stepNo}. ${name}`);
  try {
    const result = await fn();
    log.steps.push({ no: stepNo, name, ms: Date.now() - started, ok: true, ...(result ?? {}) });
    save();
  } catch (error) {
    // 실패한 순간의 화면을 열린 페이지마다 남긴다
    const pages = browser.contexts().flatMap((c) => c.pages());
    for (const [i, page] of pages.entries()) {
      await page.screenshot({ path: join(OUT, `fail-${stepNo}-${i}.png`) }).catch(() => null);
    }
    log.steps.push({ no: stepNo, name, ms: Date.now() - started, ok: false, error: String(error) });
    save();
    throw error;
  }
}

function check(name, ok, detail) {
  log.checks.push({ step: stepNo, name, ok: !!ok, detail });
  console.log(
    `  ${ok ? "✓" : "✗"} ${name}${detail === undefined ? "" : ` — ${JSON.stringify(detail)}`}`,
  );
  if (!ok) throw new Error(`check failed: ${name}`);
}

function short(value, max = 600) {
  const text = typeof value === "string" ? value : JSON.stringify(value);
  return text && text.length > max ? `${text.slice(0, max)}…` : text;
}

/** 페이지의 api 응답을 단계 이름과 함께 남긴다 */
function watch(page, who) {
  page.on("response", async (response) => {
    const url = response.url();
    if (!url.startsWith(API)) return;
    const request = response.request();
    if (request.method() === "OPTIONS") return;
    let body = null;
    try {
      body = await response.json();
    } catch {
      // 본문 없음
    }
    log.responses.push({
      step: stepNo,
      who,
      at: elapsed(),
      method: request.method(),
      path: url.slice(API.length),
      status: response.status(),
      request: short(request.postData() ?? undefined, 300),
      body: short(body),
    });
    const key = `${request.method()} ${shapeOf(url.slice(API.length))}`;
    if (response.ok() && body !== null && !firstBodies.has(key)) firstBodies.set(key, body);
  });
  page.on("console", (message) => {
    if (message.type() === "error") log.frames.push({ step: stepNo, who, console: message.text() });
  });
}

/** id·토큰 자리를 :x로 바꾼 경로 */
function shapeOf(path) {
  return path
    .split("?")[0]
    .replace(/\/s\/[^/]+/, "/s/:token")
    .replace(/[0-9a-f]{8}-[0-9a-f-]{27}/g, ":id")
    .replace(/\/my-documents\/\d+/, "/my-documents/:n")
    .replace(/\/(tasks|sections)\/\d+/, "/$1/:n");
}

// ── 계약 픽스처와 모양 비교 ─────────────────────────────────────
// 값이 아니라 키 구조를 본다. 배열은 첫 원소로, 픽스처에만 있는 키(missing)·실제에만 있는 키(extra)를 남긴다.
const FIXTURES = {
  "GET /s/:token": "candidate_entry.json",
  "POST /s/:token/consent": "candidate_session_token.json",
  "POST /s/:token/start": "candidate_start.json",
  "GET /sessions/:id/state": "state_start.json",
  "PUT /sessions/:id/my-documents/:n": "my_document_save.json",
  "POST /sessions/:id/my-documents/:n/share": "my_document_share.json",
  "POST /sessions/:id/documents/:id/open": "document_open.json",
  "PUT /sessions/:id/final/sections/:n/import": "final_section_import.json",
  "PUT /sessions/:id/tasks/:n": "task.json",
  "GET /sessions/:id/documents/interview_summary": "document.json",
  "POST /sessions/:id/assistant": "assistant_response.json",
  "POST /sessions/:id/submit": "submit.json",
  "GET /sessions/:id/debrief": "debrief.json",
  "GET /admin/catalog": "admin_catalog.json",
  "GET /admin/positions": "admin_positions.json",
  "POST /admin/positions": "admin_position_created.json",
  "POST /admin/positions/:id/invites": "admin_invite.json",
  "GET /admin/positions/:id/candidates": "admin_candidates.json",
  "GET /sessions/:id/report": "report.json",
  "GET /admin/sessions/:id/report": "report.json",
  "POST /admin/sessions/:id/review": "admin_review_response.json",
  "POST /admin/sessions/:id/report/notes": "admin_report_notes.json",
  "GET /admin/sessions/:id/record": "admin_record.json",
};

/** 경로 → 값 종류(obj·leaf). 배열은 첫 원소를 `[]`로 내려간다. null·빈 배열은 내려가지 않는다 */
function keyPaths(value, prefix = "", out = new Map()) {
  if (Array.isArray(value)) {
    if (value.length) keyPaths(value[0], `${prefix}[]`, out);
  } else if (value && typeof value === "object") {
    out.set(prefix, "obj");
    for (const [k, v] of Object.entries(value)) {
      out.set(`${prefix}.${k}`, "leaf");
      keyPaths(v, `${prefix}.${k}`, out);
    }
  }
  return out;
}

function compareShapes() {
  const dir = join(REPO, "tests", "fixtures", "contracts");
  for (const [key, file] of Object.entries(FIXTURES)) {
    const real = firstBodies.get(key);
    if (real === undefined) continue;
    const want = keyPaths(JSON.parse(readFileSync(join(dir, file), "utf8")));
    const got = keyPaths(real);
    // 부모가 양쪽 모두 객체로 있을 때만 센다(null·빈 배열이라 못 내려간 차이는 값 차이다)
    const parentOf = (k) => k.slice(0, k.lastIndexOf("."));
    // 배열 원소 자리(`x[]`)는 값(빈 배열 여부)이라 세지 않는다
    const comparable = (k) =>
      !k.endsWith("[]") && want.get(parentOf(k)) === "obj" && got.get(parentOf(k)) === "obj";
    const missing = [...want.keys()].filter((k) => k && !got.has(k) && comparable(k));
    const extra = [...got.keys()].filter((k) => k && !want.has(k) && comparable(k));
    log.shapes.push({ key, file, missing, extra });
  }
}

async function internal(method, path, body) {
  const response = await fetch(`${INTERNAL}/internal${path}`, {
    method,
    headers: { "X-Internal-Token": INTERNAL_TOKEN, "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const data = await response.json().catch(() => null);
  log.responses.push({
    step: stepNo,
    who: "internal",
    at: elapsed(),
    method,
    path: `/internal${path}`,
    status: response.status,
    request: short(body, 300),
    body: short(data),
  });
  if (!response.ok) throw new Error(`${method} ${path} → ${response.status} ${short(data)}`);
  return data;
}

async function publicApi(method, path, token, body) {
  const response = await fetch(`${API}${path}`, {
    method,
    headers: {
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(body === undefined ? {} : { "Content-Type": "application/json" }),
    },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  return { status: response.status, body: await response.json().catch(() => null) };
}

function psql(sql) {
  return execFileSync(
    "docker",
    ["exec", "infra-postgres-1", "psql", "-U", "dayzero", "-d", DB, "-Atc", sql],
    { encoding: "utf8" },
  ).trim();
}

/** 응답을 기다린다(경로 정규식·메서드) */
function waitApi(page, method, pattern, timeout = 15_000) {
  const waiting = page.waitForResponse(
    (r) =>
      r.url().startsWith(API) &&
      r.request().method() === method &&
      pattern.test(r.url().slice(API.length)),
    { timeout },
  );
  // 기다리는 동안 다른 동작이 먼저 실패해도 처리되지 않은 거부로 프로세스가 죽지 않게 한다
  waiting.catch(() => null);
  return waiting;
}

// ── WS 가로채기: 프레임 기록과 닫기 주입 ─────────────────────────
/** 페이지마다 하나. 지금 연결(route)과 다음 연결에 할 일(plan)을 들고 있다 */
async function wsTap(page, who) {
  const tap = {
    route: null,
    server: null,
    urls: [],
    /** 다음 연결 한 번에 할 일: {reject: code}(서버에 붙이지 않고 닫음) */
    plan: null,
    /** 이 시각까지 새 연결을 계속 닫는다(긴 끊김) */
    hold: 0,
    /** 이 시각까지 모든 새 연결의 상류(서버) 연결을 늦춘다(첫 연결 전 변화 재현) */
    delayUntil: 0,
    opened: 0,
    frames: [],
    /** 연결마다 {id, createdAt, delayedMs, upstreamAt, superseded} */
    conns: [],
  };
  /** 네트워크 끊김 흉내: 서버 쪽과 페이지 쪽을 함께 닫는다(route.close는 한쪽만 닫는다) */
  // 브라우저 WebSocket.close는 1000·3000~4999만 받으므로 서버 쪽은 1000으로 닫는다
  tap.drop = async () => {
    await tap.server?.close({ code: 1000, reason: "e2e drop" });
    await tap.route?.close({ code: 1012, reason: "e2e drop" });
  };
  await page.routeWebSocket(/\/ws\/sessions\//, async (ws) => {
    tap.urls.push(ws.url());
    const conn = { id: tap.conns.length + 1, createdAt: Date.now(), delayedMs: 0 };
    tap.conns.push(conn);
    // 끊김 유지 중에는 예약한 plan을 쓰지 않고 남겨 둔다
    const holding = tap.hold > Date.now();
    const plan = holding ? { reject: 1012 } : tap.plan;
    if (!holding) tap.plan = null;
    const wait = tap.delayUntil - Date.now();
    if (wait > 0) {
      await sleep(wait);
      conn.delayedMs = Date.now() - conn.createdAt;
      log.frames.push({
        step: stepNo,
        who,
        at: elapsed(),
        injected: `conn ${conn.id} delay ${conn.delayedMs}ms`,
      });
      // 기다리는 사이 화면이 새 연결을 만들었으면(개발 모드 재마운트 등) 이 연결은 버려진 것이다
      if (conn.id !== tap.conns.length) {
        conn.superseded = true;
        return;
      }
    }
    if (plan?.reject) {
      // 서버에 붙이지 않고 바로 닫는다(4401 주입, 끊김 유지)
      log.frames.push({ step: stepNo, who, at: elapsed(), injected: `close ${plan.reject}` });
      ws.close({ code: plan.reject, reason: "injected" });
      return;
    }
    const server = ws.connectToServer();
    conn.upstreamAt = Date.now();
    log.frames.push({ step: stepNo, who, at: elapsed(), upstream: `conn ${conn.id}` });
    tap.route = ws;
    tap.server = server;
    tap.opened += 1;
    server.onMessage((message) => {
      const frame = JSON.parse(String(message));
      tap.frames.push(frame);
      log.frames.push({ step: stepNo, who, at: elapsed(), dir: "in", frame: short(frame, 400) });
      ws.send(message);
    });
    ws.onMessage((message) => {
      log.frames.push({
        step: stepNo,
        who,
        at: elapsed(),
        dir: "out",
        frame: short(String(message), 300),
      });
      server.send(message);
    });
  });
  return tap;
}

async function waitFrame(tap, type, predicate = () => true, timeout = 15_000) {
  const end = Date.now() + timeout;
  for (;;) {
    const found = tap.frames.find((f) => f.type === type && predicate(f.payload));
    if (found) return found.payload;
    if (Date.now() > end) throw new Error(`frame ${type} not received`);
    await new Promise((r) => setTimeout(r, 200));
  }
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

// ── 실행 ─────────────────────────────────────────────────────
const browser = await chromium.launch({ channel: "chrome", headless: process.env.HEADED !== "1" });
const viewport = { width: 1440, height: 900 };
const adminCtx = await browser.newContext({ viewport });
adminCtx.setDefaultTimeout(15_000);
const admin = await adminCtx.newPage();
watch(admin, "admin");
const candCtx = await browser.newContext({
  viewport,
  permissions: ["clipboard-read", "clipboard-write"],
});
candCtx.setDefaultTimeout(15_000);

const email = `e2e-${Date.now()}@loop.example`;
const password = "dayzero-e2e";
let positionId = "";
let inviteUrl = "";
let token = "";
let sessionId = "";

try {
  // ── 관리자 ──
  await step("관리자 가입", async () => {
    await admin.goto(`${WEB}/admin/signup`);
    await admin.getByLabel("회사 이름").fill("루프랩 e2e");
    await admin.getByLabel("이메일").fill(email);
    await admin.getByLabel("비밀번호").fill(password);
    const signed = waitApi(admin, "POST", /^\/admin\/auth\/signup$/);
    await admin.getByRole("button", { name: "가입하고 시작" }).click();
    check("signup 200", (await signed).status() === 200);
    await admin.waitForURL(/\/admin\/positions/);
    return { shot: await shot(admin, "signup") };
  });

  await step("관리자 로그인", async () => {
    await admin.evaluate(() => localStorage.clear());
    await admin.goto(`${WEB}/admin/login`);
    await admin.getByLabel("이메일").fill(email);
    await admin.getByLabel("비밀번호").fill(password);
    const logged = waitApi(admin, "POST", /^\/admin\/auth\/login$/);
    await admin.getByRole("button", { name: "로그인" }).click();
    check("login 200", (await logged).status() === 200);
    await admin.waitForURL(/\/admin\/positions/);
    return { shot: await shot(admin, "login") };
  });

  await step("채용 건 생성(요소 5개, 회사 문서 표시)", async () => {
    await admin.goto(`${WEB}/admin/positions/new`);
    const adminJwt = await admin.evaluate(() => localStorage.getItem("dayzero.admin.token"));
    const catalog = (await publicApi("GET", "/admin/catalog", adminJwt)).body;
    const titles = catalog.missions[0].documents.map((d) => d.title);
    check("catalog.documents", titles.length > 0, titles);
    await admin.getByText(`회사 문서 ${titles.join(" · ")}`).waitFor();
    check("5요소 기본 선택", (await admin.getByRole("checkbox", { checked: true }).count()) === 5);
    await admin.getByLabel("채용 건 이름").fill("PM 인턴 e2e");
    const created = waitApi(admin, "POST", /^\/admin\/positions$/);
    const s = await shot(admin, "position-new");
    await admin.getByRole("button", { name: "채용 건 만들기" }).click();
    const body = await (await created).json();
    positionId = body.id;
    check("elements 5", body.elements.length === 5, body.catalog_version);
    await admin.waitForURL(new RegExp(`/admin/positions/${positionId}`));
    return { shot: s, position_id: positionId, catalog_version: body.catalog_version };
  });

  await step("초대 링크 만들기", async () => {
    await admin.getByLabel("별칭").fill("지원자A");
    await admin.getByLabel("이메일").fill("a@example.com");
    const invited = waitApi(admin, "POST", /\/invites$/);
    await admin.getByRole("button", { name: "초대 링크 만들기" }).click();
    const body = await (await invited).json();
    inviteUrl = body.invite_url;
    await admin.getByText(inviteUrl).waitFor();
    check("invite_url", inviteUrl.includes("/s/"), inviteUrl);
    return { shot: await shot(admin, "invite") };
  });

  await step("초대 링크 입장 화면", async () => {
    const page = await candCtx.newPage();
    watch(page, "invitee");
    const entry = waitApi(page, "GET", /^\/s\/[^/]+$/);
    await page.goto(inviteUrl);
    const body = await (await entry).json();
    check("status invited", body.status === "invited", body.company_name);
    await page.getByRole("button", { name: "다음" }).waitFor();
    const s = await shot(page, "invite-entry");
    await page.close();
    return { shot: s };
  });

  // ── 6분 테스트 세션 ──
  await step("6분 테스트 세션 만들기(내부 API) → 관리자 회사로 옮김", async () => {
    const created = await internal("POST", "/test/sessions", {
      elements: ELEMENTS,
      session_minutes: 6,
      alias: "지원자E2E",
    });
    token = created.token;
    sessionId = created.session_id;
    // 테스트 API는 고정 회사에 채용 건을 만든다. 관리자 화면에서 리포트를 보려고 관리자 회사로 옮긴다
    const moved = psql(
      `UPDATE positions SET company_id = (SELECT company_id FROM admins WHERE email = '${email}'), ` +
        `name = 'e2e 6분 세션' WHERE id = (SELECT i.position_id FROM sessions s JOIN invites i ON i.id = s.invite_id WHERE s.id = '${sessionId}') RETURNING id`,
    );
    check("position moved", moved.length > 0, moved);
    return { session_id: sessionId };
  });

  const pageA = await candCtx.newPage();
  watch(pageA, "A");
  const tapA = await wsTap(pageA, "A");

  await step("지원자 입장 → 동의 → 시작 → 오피스", async () => {
    await pageA.goto(`${WEB}/s/${token}`);
    await pageA.getByRole("button", { name: "다음" }).click();
    await pageA.getByLabel("위 내용에 동의").check();
    const consent = waitApi(pageA, "POST", /\/consent$/);
    await pageA.getByRole("button", { name: "동의하고 계속" }).click();
    check("consent 200", (await consent).status() === 200);
    const s1 = await shot(pageA, "waiting");
    const started = waitApi(pageA, "POST", /\/start$/);
    const state = waitApi(pageA, "GET", /\/state$/);
    await pageA.getByRole("button", { name: /시작/ }).click();
    check("start 200", (await started).status() === 200);
    const snap = await (await state).json();
    check("state alias", snap.session.alias === "지원자E2E", snap.session.alias);
    check("tasks 5 null", snap.tasks.length === 5 && snap.tasks.every((t) => t.assignee === null));
    await waitFrame(tapA, "message.new").catch(() => null);
    await pageA.getByRole("navigation", { name: "채널" }).waitFor();
    await sleep(800);
    return { shots: [s1, await shot(pageA, "office")] };
  });

  const work = pageA.getByRole("complementary", { name: "작업" });
  const tab = (page, name) =>
    page.getByRole("complementary", { name: "작업" }).getByRole("tab", { name }).click();
  const jwtOf = (page, link = token) =>
    page.evaluate((t) => sessionStorage.getItem(`dz:${t}`), link);
  const assign = async (page, part, label) => {
    await page.getByRole("button", { name: new RegExp(`^${part}번 담당:`) }).click();
    await page.getByRole("menuitem", { name: label, exact: true }).click();
  };

  await step("보드 분업: 조건 위반 422 문장 → 확정(division.confirmed)", async () => {
    await tab(pageA, "보드");
    for (const [part, who] of [
      [1, "나"],
      [3, "둘 다 (나 + 도현)"],
      [4, "도현"],
      [5, "도현"],
    ]) {
      const put = waitApi(pageA, "PUT", new RegExp(`/tasks/${part}$`));
      await assign(pageA, part, who);
      check(`PUT tasks/${part}`, (await put).status() === 200);
    }
    // 2번 상세를 연 채로 2번을 동료에게 주면 다섯 장이 다 차면서 division_min을 어긴다
    await work.getByRole("button", { name: "2 사용자 인터뷰에서 찾은 근거", exact: true }).click();
    const bad = waitApi(pageA, "PUT", /\/tasks\/2$/);
    await assign(pageA, 2, "도현");
    const badResponse = await bad;
    const badBody = await badResponse.json();
    check("422 invalid_division", badResponse.status() === 422, badBody.error);
    await work.getByRole("alert").filter({ hasText: badBody.error.message }).waitFor();
    const s1 = await shot(pageA, "board-422");
    const good = waitApi(pageA, "PUT", /\/tasks\/2$/);
    await assign(pageA, 2, "나");
    check("PUT tasks/2 200", (await good).status() === 200);
    const confirmed = await waitFrame(tapA, "division.confirmed");
    check("division.confirmed", confirmed.decided_by === "candidate", confirmed.parts);
    await sleep(500);
    return { shots: [s1, await shot(pageA, "board-confirmed")] };
  });

  await step("내 문서 저장(1초 디바운스) → 보내기(note)", async () => {
    await tab(pageA, "내 문서");
    await work.getByRole("button", { name: /^1 문제 정의와 대상 사용자 ./ }).click();
    const saved = waitApi(pageA, "PUT", /\/my-documents\/1$/);
    const typedAt = Date.now();
    await work
      .getByLabel("1. 문제 정의와 대상 사용자 본문")
      .fill("재참여가 떨어진 3개월 차 사용자를 대상으로 문제를 정의한다.");
    const savedResponse = await saved;
    const waited = Date.now() - typedAt;
    const body = await savedResponse.json();
    check("debounce ≥ 1s", waited >= 1000, { waited, revision: body.revision });
    await work.getByRole("button", { name: "v1 보내기" }).click();
    await pageA.getByLabel("문서와 함께 보낼 한마디").fill("1번 초안 올려요. 의견 주세요.");
    const shared = waitApi(pageA, "POST", /\/my-documents\/1\/share$/);
    await pageA.getByRole("button", { name: "v1 보내기" }).last().click();
    const share = await (await shared).json();
    check("share v1", share.version === 1, share);
    const frame = await waitFrame(tapA, "document.shared", (p) => p.by === "candidate");
    check("document.shared(candidate)", frame.message_id === share.message_id);
    // 2번은 보내지 않고 저장만(최종본 vnull 가져오기용)
    await work.getByRole("button", { name: "← 내 문서" }).click();
    await work.getByRole("button", { name: /^2 사용자 인터뷰에서 찾은 근거 ./ }).click();
    const saved2 = waitApi(pageA, "PUT", /\/my-documents\/2$/);
    await work
      .getByLabel("2. 사용자 인터뷰에서 찾은 근거 본문")
      .fill("인터뷰 5명 중 4명이 첫 주 이후 알림을 껐다.");
    check("PUT my-documents/2", (await saved2).status() === 200);
    await sleep(500);
    return { shot: await shot(pageA, "share") };
  });

  let colleagueDoc = null;
  await step("동료 문서 받기(내부 docs/send) → 열기(open) → 답글(reply_to_doc)", async () => {
    // FakeAgentRunner는 문서를 보내지 않는다. 동료 그래프의 send_document를 내부 API로 대신한다
    colleagueDoc = await internal("POST", `/sessions/${sessionId}/docs/send`, {
      part_no: 4,
      content: "비슷한 서비스 사례\n- 런데이: 주간 목표 알림\n- 나이키 런: 친구 챌린지",
      channel: "team",
      run_id: randomUUID(),
      seq: 40,
    });
    const frame = await waitFrame(tapA, "document.shared", (p) => p.by === "colleague");
    check("document.shared(colleague)", frame.doc_id === colleagueDoc.doc_id, frame);
    await waitFrame(tapA, "message.new", (m) => m.shared_doc?.doc_id === colleagueDoc.doc_id);
    const opened = waitApi(pageA, "POST", /\/documents\/[^/]+\/open$/);
    // 문서 카드(한 장이면 큰 카드, 묶이면 작은 카드)
    await pageA.getByRole("button", { name: /비슷한 서비스 사례.*v1.*열기/ }).click();
    const openBody = await (await opened).json();
    check(
      "open 200",
      openBody.version === 1 && openBody.content.includes("런데이"),
      openBody.t_min,
    );
    await pageA.getByText("런데이: 주간 목표 알림").waitFor();
    const s1 = await shot(pageA, "doc-open");
    await pageA.getByRole("button", { name: "답글 쓰기" }).click();
    await pageA.getByText(/v1에 답/).waitFor();
    const composer = pageA.getByPlaceholder(/에 메시지 보내기/);
    await composer.fill("4번 사례 좋아요. 재참여 지표도 같이 적어 주세요.");
    await composer.press("Enter");
    const ack = await waitFrame(tapA, "message.ack");
    const mine = await waitFrame(tapA, "message.new", (m) => m.id === ack.message_id);
    check("reply_to_doc", mine.reply_to_doc?.doc_id === colleagueDoc.doc_id, mine.reply_to_doc);
    const reply = await waitFrame(
      tapA,
      "message.new",
      (m) => m.sender === "colleague" && !m.shared_doc,
    );
    check("동료 응답(FakeAgentRunner)", !!reply.content, reply.content);
    await sleep(500);
    return { shots: [s1, await shot(pageA, "reply")] };
  });

  await step("최종본: 동료 v1·내 문서(현재 저장본 vnull) 가져오기 → 편집", async () => {
    await tab(pageA, "내 문서");
    await work
      .getByRole("button", { name: "← 내 문서" })
      .click()
      .catch(() => null);
    await work.getByRole("button", { name: /^최종본/ }).click();
    const section = (title) =>
      work.locator("section").filter({ has: pageA.getByRole("heading", { name: title }) });
    const pick = async (title, item) => {
      await section(title).getByRole("button", { name: "가져오기" }).click();
      const imported = waitApi(pageA, "PUT", /\/final\/sections\/\d\/import$/);
      await pageA.getByRole("menuitem", { name: new RegExp(`^${item}`) }).click();
      const response = await imported;
      return {
        status: response.status(),
        request: JSON.parse(response.request().postData()),
        body: await response.json(),
      };
    };
    const four = await pick("비슷한 서비스 사례", "4. 비슷한 서비스 사례 v1");
    check("import 4 ← 동료 v1", four.status === 200 && four.request.version === 1, four.body);
    const two = await pick("사용자 인터뷰에서 찾은 근거", "2. 사용자 인터뷰에서 찾은 근거");
    check("import 2 ← 내 문서 vnull", two.status === 200 && two.request.version === null, two.body);
    const one = await pick("문제 정의와 대상 사용자", "1. 문제 정의와 대상 사용자");
    check("import 1 ← 내 문서", one.status === 200, one.body);
    const saved = waitApi(pageA, "PUT", /\/my-documents\/final$/);
    await work
      .getByLabel("최종본 4. 비슷한 서비스 사례")
      .fill(`${four.body.content}\n- 재참여 지표: 4주 잔존율`);
    check("PUT final", (await saved).status() === 200);
    await sleep(400);
    return { shot: await shot(pageA, "final") };
  });

  await step(
    "저장: 실패 표시 유지·제출 차단·해제 → 느린 PUT 중 추가 입력·재연결·flush 겹침",
    async () => {
      // 저장 PUT만 500으로 바꾼다(서버에는 가지 않음)
      const failing = (route) =>
        route.fulfill({
          status: 500,
          contentType: "application/json",
          body: JSON.stringify({ error: { code: "internal", message: "e2e 저장 실패" } }),
        });
      await pageA.route(/\/my-documents\/final$/, failing);
      const field = work.getByLabel("최종본 5. 성공 지표와 출시 일정");
      const failText = work.getByText("저장 실패 · 다음 편집 때 다시 저장");
      await field.fill("4주 잔존율 25% 목표");
      await failText.waitFor({ timeout: 5000 });
      // 다시 고쳐 저장을 다시 예약해도(저장 중) 실패 안내가 남는다
      await field.fill("4주 잔존율 25% 목표, 6주 차 출시");
      await sleep(300);
      check("재편집 중 실패 유지", await failText.isVisible());
      const s1 = await shot(pageA, "final-save-failed");
      await work.getByRole("button", { name: "제출", exact: true }).click();
      let submitted = false;
      const onSubmit = (r) => r.url().endsWith("/submit") && (submitted = true);
      pageA.on("request", onSubmit);
      await pageA.getByRole("dialog").getByRole("button", { name: "제출" }).click();
      await pageA.getByText(/저장되지 않아 제출을\(를\) 멈췄어요/).waitFor();
      pageA.off("request", onSubmit);
      check("제출 차단(submit 요청 없음)", !submitted);
      await pageA.unroute(/\/my-documents\/final$/, failing);
      const saved = waitApi(pageA, "PUT", /\/my-documents\/final$/);
      await field.fill("4주 잔존율 25% 목표, 6주 차 출시.");
      check("다시 저장 200", (await saved).status() === 200);
      await failText.waitFor({ state: "hidden" });
      check("성공 뒤 실패 안내 해제", !(await failText.isVisible()));

      // 느린 저장(PUT 2.5초) 중 추가 입력 → 재연결(/state 재동기화) → flush(보내기·가져오기)가 겹쳐도
      // 내 문서·최종본의 최신 본문이 마지막 요청에 담기고, flush 뒤 동작은 그 저장이 끝난 다음에 나간다
      const puts = { doc: [], final: [] };
      const slow = async (route) => {
        const request = route.request();
        const key = request.url().endsWith("/final") ? "final" : "doc";
        const entry = { startedAt: Date.now(), body: JSON.parse(request.postData()) };
        puts[key].push(entry);
        await sleep(2500);
        await route.continue();
        entry.doneAt = Date.now();
      };
      const SLOW = /\/my-documents\/(2|final)$/;
      await pageA.route(SLOW, slow);
      const until = async (cond) => {
        for (let i = 0; i < 100 && !cond(); i += 1) await sleep(100);
      };
      const B2 = "4주 잔존율 25%, 6주 차 출시, 8주 차 점검";
      await field.fill("4주 잔존율 25%, 6주 차 출시(느린 저장 1)");
      await until(() => puts.final.length === 1);
      await field.fill(B2); // 첫 PUT이 도는 중에 더 고친다
      await work.getByRole("button", { name: "← 내 문서" }).click();
      await work.getByRole("button", { name: /^2 사용자 인터뷰에서 찾은 근거 ./ }).click();
      const doc2 = work.getByLabel("2. 사용자 인터뷰에서 찾은 근거 본문");
      const A2 = "인터뷰 5명 중 4명이 첫 주 이후 알림을 껐다. 2명은 다시 켜는 법을 몰랐다.";
      await doc2.fill("인터뷰 5명 중 4명이 첫 주 이후 알림을 껐다.(느린 저장 1)");
      await until(() => puts.doc.length === 1);
      await doc2.fill(A2);
      // 저장이 도는 사이 재연결: 재동기화 스냅샷이 서버의 옛 본문으로 덮지 않아야 한다
      const resync = waitApi(pageA, "GET", /\/state$/, 15_000);
      await tapA.drop();
      await resync;
      check("재동기화 뒤 내 문서 최신 본문 유지", (await doc2.inputValue()) === A2);
      // flush ①: 2번 보내기는 2번 저장이 끝난 뒤에 나간다
      let shareAt = 0;
      const onShare = (r) => /\/my-documents\/2\/share$/.test(r.url()) && (shareAt = Date.now());
      pageA.on("request", onShare);
      const shared = waitApi(pageA, "POST", /\/my-documents\/2\/share$/, 20_000);
      await work.getByRole("button", { name: "v1 보내기" }).click();
      await pageA.getByRole("button", { name: "v1 보내기" }).last().click();
      check("2번 보내기 200", (await shared).status() === 200);
      pageA.off("request", onShare);
      const lastDoc = puts.doc.at(-1);
      check("내 문서 마지막 PUT = 최신 본문", lastDoc.body.content === A2, {
        puts: puts.doc.length,
      });
      check("보내기는 마지막 저장 뒤", lastDoc.doneAt && shareAt >= lastDoc.doneAt);
      // flush ②: 최종본 3번 가져오기는 최종본 저장이 끝난 뒤에 나간다
      await work.getByRole("button", { name: "← 내 문서" }).click();
      await work.getByRole("button", { name: /^최종본/ }).click();
      let importAt = 0;
      const onImport = (r) =>
        /\/final\/sections\/3\/import$/.test(r.url()) && (importAt = Date.now());
      pageA.on("request", onImport);
      const imported = waitApi(pageA, "PUT", /\/final\/sections\/3\/import$/, 20_000);
      await work
        .locator("section")
        .filter({ has: pageA.getByRole("heading", { name: "핵심 기능 제안" }) })
        .getByRole("button", { name: "가져오기" })
        .click();
      await pageA.getByRole("menuitem", { name: /^1\. 문제 정의와 대상 사용자/ }).click();
      check("3번 가져오기 200", (await imported).status() === 200);
      pageA.off("request", onImport);
      const lastFinal = puts.final.at(-1);
      const five = lastFinal.body.sections.find((x) => x.part_no === 5);
      check("최종본 마지막 PUT = 최신 본문", five.content === B2, { puts: puts.final.length });
      check("가져오기는 마지막 최종본 저장 뒤", lastFinal.doneAt && importAt >= lastFinal.doneAt);
      await pageA.unroute(SLOW, slow);
      // 서버에 남은 값
      const mine = (
        await publicApi("GET", `/sessions/${sessionId}/my-documents`, await jwtOf(pageA))
      ).body;
      check("서버 2번 = 최신", mine.documents.find((d) => d.part_no === 2).content === A2);
      const serverFinal = Object.fromEntries(mine.final.sections.map((x) => [x.part_no, x]));
      check("서버 최종본 5번 = 최신", serverFinal[5].content === B2);
      check(
        "서버 최종본 3번 = 가져옴",
        serverFinal[3].source_version === null && !!serverFinal[3].source_doc_id,
      );
      return { shots: [s1, await shot(pageA, "slow-save")] };
    },
  );

  await step("어시스턴트: 응답 표시·복사 → 60회 초과 429 안내", async () => {
    await tab(pageA, "어시스턴트");
    const asked = waitApi(pageA, "POST", /\/assistant$/);
    await pageA.getByLabel("어시스턴트 요청").fill("지표 현황에서 재참여율을 요약해 줘");
    await pageA.getByRole("button", { name: "묻기" }).click();
    const reply = await (await asked).json();
    check("assistant 200", !!reply.content, reply.content);
    await work.getByText(reply.content).waitFor();
    await work.getByRole("button", { name: "복사" }).first().click();
    const copied = await pageA.evaluate(() => navigator.clipboard.readText());
    check("복사", copied === reply.content);
    const s1 = await shot(pageA, "assistant");
    // 한도(60회)까지 직접 채운 뒤 화면에서 한 번 더 묻는다
    const jwt = await jwtOf(pageA);
    let calls = 1;
    for (; calls < 60; calls += 1) {
      const r = await publicApi("POST", `/sessions/${sessionId}/assistant`, jwt, {
        prompt: `채우기 ${calls}`,
      });
      if (r.status !== 200) throw new Error(`assistant ${calls + 1} → ${r.status}`);
    }
    const limited = waitApi(pageA, "POST", /\/assistant$/);
    await pageA.getByLabel("어시스턴트 요청").fill("한 번 더");
    await pageA.getByRole("button", { name: "묻기" }).click();
    const limitedResponse = await limited;
    check(
      "61번째 429 assistant_limit",
      limitedResponse.status() === 429,
      (await limitedResponse.json()).error,
    );
    await work.getByRole("alert").filter({ hasText: "한도(60회)" }).waitFor();
    return { shots: [s1, await shot(pageA, "assistant-429")] };
  });

  await step("재연결 ①: WS 끊김 → 3초 뒤 재접속 → /state 갱신(connection_gaps)", async () => {
    const before = tapA.opened;
    const closedAt = Date.now();
    await tapA.drop();
    await pageA
      .getByText("연결 끊김 · 연결되면 전송")
      .waitFor({ timeout: 2000 })
      .catch(() => null);
    const s1 = await shot(pageA, "ws-dropped");
    const state = waitApi(pageA, "GET", /\/state$/, 10_000);
    const snap = await (await state).json();
    const delay = Date.now() - closedAt;
    check("재접속 ≥ 3초", tapA.opened === before + 1 && delay >= 3000, { delay });
    check("connection_gaps", snap.connection_gaps.length >= 1, snap.connection_gaps);
    await pageA.getByText("연결이 다시 이어졌어요").waitFor();
    return { shots: [s1, await shot(pageA, "ws-reconnected")] };
  });

  await step("재연결 ②: close 4401 → POST /resume → 새 토큰으로 재접속", async () => {
    // 서버가 실제로 4401을 주는지 먼저 확인(위조 토큰)
    const code = await new Promise((resolve) => {
      const ws = new WebSocket(
        `${API.replace("http", "ws")}/ws/sessions/${sessionId}?token=forged`,
      );
      ws.onclose = (event) => resolve(event.code);
    });
    check("서버 4401(위조 토큰)", code === 4401);
    const before = tapA.urls.length;
    const oldToken = new URL(tapA.urls.at(-1)).searchParams.get("token");
    tapA.plan = { reject: 4401 };
    const resumed = waitApi(pageA, "POST", /\/resume$/, 15_000);
    await tapA.drop();
    check("resume 200", (await resumed).status() === 200);
    for (let i = 0; i < 50 && tapA.urls.length < before + 2; i += 1) await sleep(100);
    const newToken = new URL(tapA.urls.at(-1)).searchParams.get("token");
    check("새 토큰으로 재접속", tapA.urls.length === before + 2 && newToken !== oldToken);

    // 일시 장애: 재발급이 한 번 503이면 오피스와 입력 중인 글을 그대로 두고 3초 뒤 재발급을 다시 한다
    const draft = "아직 보내지 않은 입력";
    const composer = pageA.getByPlaceholder(/에 메시지 보내기/);
    await composer.fill(draft);
    let failedOnce = false;
    const flaky = (route) => {
      if (failedOnce) return route.continue();
      failedOnce = true;
      return route.fulfill({
        status: 503,
        contentType: "application/json",
        body: JSON.stringify({ error: { code: "unavailable", message: "e2e 일시 장애" } }),
      });
    };
    await pageA.route(/\/s\/[^/]+\/resume$/, flaky);
    let relanded = false;
    const onRequest = (r) => {
      if (
        r.url().startsWith(API) &&
        r.method() === "GET" &&
        /^\/s\/[^/]+$/.test(new URL(r.url()).pathname)
      )
        relanded = true;
    };
    pageA.on("request", onRequest);
    const before2 = tapA.urls.length;
    tapA.plan = { reject: 4401 };
    const firstTry = waitApi(pageA, "POST", /\/resume$/);
    await tapA.drop();
    check("resume 503(주입)", (await firstTry).status() === 503);
    const retried = await waitApi(pageA, "POST", /\/resume$/, 15_000);
    check("3초 뒤 재발급 200", retried.status() === 200);
    for (let i = 0; i < 50 && tapA.urls.length < before2 + 2; i += 1) await sleep(100);
    pageA.off("request", onRequest);
    await pageA.unroute(/\/s\/[^/]+\/resume$/, flaky);
    check("재발급 뒤 재접속", tapA.urls.length === before2 + 2);
    check(
      "오피스 유지(링크 재판정 없음)",
      !relanded && (await pageA.getByRole("navigation", { name: "채널" }).isVisible()),
    );
    check("입력 중인 글 유지", (await composer.inputValue()) === draft);
    await composer.fill("");
    return {};
  });

  await step("회사 문서 지연 공개: document.released → 자료 탭 '공개됨'", async () => {
    const released = await waitFrame(tapA, "document.released", () => true, 240_000);
    check("document.released", !!released.doc_id, released);
    await tab(pageA, "자료");
    const row = work.getByRole("button", { name: new RegExp(released.title) });
    await row.getByText("공개됨").waitFor();
    const read = waitApi(pageA, "GET", new RegExp(`/documents/${released.doc_id}$`));
    await row.click();
    check("공개 문서 열람 200", (await read).status() === 200);
    await sleep(300);
    return { shot: await shot(pageA, "released") };
  });

  const pageB = await candCtx.newPage();
  watch(pageB, "B");
  const tapB = await wsTap(pageB, "B");

  await step("재연결 ③: 다른 창 접속 → 이전 창 session.replaced(4000) 가림막", async () => {
    const resumed = waitApi(pageB, "POST", /\/resume$/);
    await pageB.goto(`${WEB}/s/${token}`);
    check("B resume 200", (await resumed).status() === 200);
    await waitFrame(tapA, "session.replaced");
    await pageA.getByRole("button", { name: "이 창에서 다시 열기" }).waitFor();
    const s1 = await shot(pageA, "replaced");
    await pageB.getByRole("navigation", { name: "채널" }).waitFor();
    await pageA.close();
    return { shot: s1 };
  });

  const workB = pageB.getByRole("complementary", { name: "작업" });
  await step("제출 → reporting(deadline_at·5분 카운트)", async () => {
    await tab(pageB, "내 문서");
    await workB.getByRole("button", { name: /^최종본/ }).click();
    await workB.getByRole("button", { name: "제출", exact: true }).click();
    const submitted = waitApi(pageB, "POST", /\/submit$/);
    await pageB.getByRole("dialog").getByRole("button", { name: "제출" }).click();
    const body = await (await submitted).json();
    check("submit → reporting", body.status === "reporting" && !!body.deadline_at, body);
    await sleep(800);
    return { shot: await shot(pageB, "reporting") };
  });

  await step("reporting 재입장(새로고침 → resume → state.deadline_at)", async () => {
    const resumed = waitApi(pageB, "POST", /\/resume$/);
    const state = waitApi(pageB, "GET", /\/state$/);
    await pageB.reload();
    check("resume 200", (await resumed).status() === 200);
    const snap = await (await state).json();
    check(
      "state reporting",
      snap.session.status === "reporting" && !!snap.session.deadline_at,
      snap.session,
    );
    await pageB.getByRole("navigation", { name: "채널" }).waitFor();
    await sleep(800);
    return { shot: await shot(pageB, "reporting-reentry") };
  });

  await step("reporting 중 1분 넘게 끊김 → 재접속 시 끊김 줄", async () => {
    tapB.hold = Date.now() + 65_000;
    await tapB.drop();
    await sleep(66_000);
    const state = waitApi(pageB, "GET", /\/state$/, 15_000);
    const snap = await (await state).json();
    const long = snap.connection_gaps.find((g) => g.to_t_min - g.from_t_min >= 1);
    check("1분 넘는 gap", !!long, snap.connection_gaps);
    await pageB
      .getByText(/연결이 끊겼어요/)
      .first()
      .waitFor();
    return { shot: await shot(pageB, "gap-line") };
  });

  await step(
    "보고 메시지 → (그래프 대신) 분류 kind=report·complete → session.ended → 디브리핑",
    async () => {
      const composer = pageB.getByPlaceholder(/에 메시지 보내기/);
      await composer.fill("팀장님, 최종본 제출했습니다. 4번은 도현님 v1을 가져와 지표를 더했어요.");
      await composer.press("Enter");
      const ack = await waitFrame(tapB, "message.ack");
      // 실제 그래프는 respond 앞 분류를 저장하고 complete를 부른다(agent-session 몫)
      await internal("PUT", `/sessions/${sessionId}/messages/${ack.message_id}/classification`, {
        recipient: "manager",
        kind: "report",
      });
      await internal("POST", `/sessions/${sessionId}/complete`);
      const ended = await waitFrame(tapB, "session.ended");
      check("session.ended", !!ended.reason, ended);
      const debrief = waitApi(pageB, "GET", /\/debrief$/, 10_000);
      const body = await (await debrief).json();
      check("debrief final", !!body.final?.sections?.length, body.survey);
      await pageB.getByText("내가 제출한 최종본").waitFor();
      return { shot: await shot(pageB, "debrief") };
    },
  );

  await step("디브리핑 설문 POST", async () => {
    for (const fieldset of await pageB.locator("fieldset").all()) {
      await fieldset.getByRole("button", { name: "4", exact: true }).click();
    }
    const posted = waitApi(pageB, "POST", /\/debrief\/survey$/);
    await pageB.getByRole("button", { name: "설문 보내기" }).click();
    check("survey 200", (await posted).status() === 200);
    await pageB.getByText("설문 제출 완료").waitFor();
    return { shot: await shot(pageB, "survey") };
  });

  // ── 경계 사례(두 번째 6분 세션): 첫 WS 연결 전 변화, 4401 뒤 resume 409 ──
  let token2 = "";
  let session2 = "";
  const pageC = await candCtx.newPage();
  watch(pageC, "C");
  const tapC = await wsTap(pageC, "C");

  await step("경계 ①: 첫 WS 연결 전에 온 메시지를 첫 연결에서 따라잡음", async () => {
    const created = await internal("POST", "/test/sessions", {
      elements: ELEMENTS,
      session_minutes: 6,
      alias: "지원자경계",
    });
    token2 = created.token;
    session2 = created.session_id;
    const { session_token } = (await publicApi("POST", `/s/${token2}/consent`)).body;
    check(
      "start 200",
      (await publicApi("POST", `/s/${token2}/start`, session_token)).status === 200,
    );
    const TEXT = "첫 연결 전에 보낸 팀장 메시지";
    const has = (snap) => snap.messages.some((m) => m.content === TEXT);
    // 이 창의 모든 새 연결을 2.5초 늦춘다(개발 모드 재마운트로 연결이 둘 생겨도 우회하지 못하게)
    const startedAt = Date.now();
    tapC.delayUntil = startedAt + 2500;
    const states = [];
    const onState = async (r) => {
      if (!r.url().startsWith(API) || !/\/state$/.test(r.url())) return;
      states.push({ at: Date.now(), has: has(await r.json()) });
    };
    pageC.on("response", onState);
    const firstState = waitApi(pageC, "GET", /\/state$/);
    await pageC.goto(`${WEB}/s/${token2}`);
    const first = await (await firstState).json();
    check("① 최초 snapshot에 없음", !has(first));
    await internal("POST", `/sessions/${session2}/messages`, {
      channel: "team",
      sender: "manager",
      content: TEXT,
      run_id: randomUUID(),
      seq: 1,
    });
    const savedAt = Date.now();
    check(
      "② 상류 연결 전에 저장",
      !tapC.conns.some((c) => c.upstreamAt && c.upstreamAt <= savedAt),
    );
    await pageC.getByText(TEXT).waitFor({ timeout: 10_000 });
    pageC.off("response", onState);
    const live = tapC.conns.find((c) => c.upstreamAt);
    check("③ 상류 연결은 2.5초 지연 뒤", live && live.upstreamAt - startedAt >= 2500, {
      conn: live?.id,
      delayedMs: live?.delayedMs,
      upstreamAfterStartMs: live && live.upstreamAt - startedAt,
    });
    const after = states.find((x) => x.has);
    check("④ 연결 뒤 state에 있음", after && after.at >= live.upstreamAt, {
      stateAfterUpstreamMs: after && after.at - live.upstreamAt,
    });
    return {
      shot: await shot(pageC, "first-open"),
      connections: tapC.conns.map((c) => ({
        id: c.id,
        delayedMs: c.delayedMs,
        upstream: !!c.upstreamAt,
        superseded: !!c.superseded,
      })),
    };
  });

  await step(
    "경계 ②: 끊긴 사이 세션 종료 → 4401 → resume 409 → 링크 재판정 → 디브리핑",
    async () => {
      const jwt = await jwtOf(pageC, token2);
      const submitted = await publicApi("POST", `/sessions/${session2}/submit`, jwt);
      check("submit reporting", submitted.body.status === "reporting", submitted.body);
      tapC.hold = Date.now() + 2500;
      tapC.plan = { reject: 4401 };
      await tapC.drop();
      await internal("POST", `/sessions/${session2}/complete`);
      const resumed = await waitApi(pageC, "POST", /\/resume$/, 15_000);
      check("resume 409", resumed.status() === 409);
      const entry = await waitApi(pageC, "GET", /^\/s\/[^/]+$/, 10_000);
      const landed = (await entry.json()).status;
      // 워커가 곧바로 draft를 만들면 report_ready다. 어느 쪽이든 종료 상태로 판정되어야 한다
      check(
        "링크 재판정(종료 상태)",
        !["invited", "in_progress", "reporting"].includes(landed),
        landed,
      );
      await pageC.getByText("수고하셨습니다").waitFor();
      const s1 = await shot(pageC, "resume-409-debrief");
      await pageC.close();
      return { shot: s1 };
    },
  );

  // ── 관리자 리포트 ──
  await step("관리자: 지원자 목록 → 리포트 draft(워커)", async () => {
    await admin.goto(`${WEB}/admin/positions`);
    await admin.getByText("e2e 6분 세션").click();
    const deadline = Date.now() + 240_000;
    for (;;) {
      // 목록이 다 그려진 뒤에 리포트 버튼을 본다
      await admin.getByText("지원자E2E").first().waitFor();
      if (await admin.getByRole("button", { name: "리포트" }).count()) break;
      if (Date.now() > deadline) throw new Error("report not ready");
      await sleep(5000);
      await admin.reload();
    }
    const s1 = await shot(admin, "candidates");
    const loaded = waitApi(admin, "GET", /\/report$/);
    await admin.getByRole("button", { name: "리포트" }).click();
    const report = await (await loaded).json();
    check("report draft", report.stage === "draft", {
      alias: report.alias,
      purge_at: report.purge_at,
    });
    await admin.getByRole("button", { name: "검토 완료" }).waitFor();
    return { shots: [s1, await shot(admin, "report-draft")] };
  });

  await step("관리자: 조정·메모 → 검토 완료 → final → 메모 추가", async () => {
    const select = admin.locator("select[aria-label$='담당자 값']").first();
    if (!(await select.isVisible()))
      await admin.locator("details[id^='card-'] > summary").first().click();
    const current = await select.inputValue();
    await select.selectOption(current === "0" ? "1" : "0");
    await admin.getByLabel("조정 메모").first().fill("면접에서 다시 확인");
    await admin.getByLabel("검토자 이름").fill("담당자 e2e");
    await admin.getByRole("button", { name: "검토 완료" }).click();
    const reviewed = waitApi(admin, "POST", /\/review$/);
    await admin.getByRole("dialog").getByRole("button", { name: "검토 완료" }).click();
    const review = await reviewed;
    check("review 200", review.status() === 200, await review.json());
    const deadline = Date.now() + 120_000;
    let stage = "";
    while (Date.now() < deadline) {
      const r = await admin.waitForResponse(
        (x) => x.url().endsWith("/report") && x.url().startsWith(API),
        { timeout: 30_000 },
      );
      stage = (await r.json()).stage;
      if (stage === "final") break;
    }
    check("final", stage === "final");
    await admin.getByLabel("리포트 메모 추가").fill("면접 때 4번 사례 출처 질문");
    await admin.getByLabel("작성자").fill("담당자 e2e");
    const noted = waitApi(admin, "POST", /\/report\/notes$/);
    await admin.getByRole("button", { name: "메모 추가" }).click();
    check("notes 200", (await noted).status() === 200);
    await admin.getByText("면접 때 4번 사례 출처 질문").waitFor();
    return { shot: await shot(admin, "report-final") };
  });

  await step("관리자: 근거 → 전체 기록(record_ref 하이라이트)·삭제 예정일", async () => {
    const link = admin.getByRole("link", { name: "기록에서 보기" }).first();
    const href = await link.getAttribute("href");
    const record = waitApi(admin, "GET", /\/record$/);
    await link.click();
    const entries = await (await record).json();
    const anchor = href.split("#")[1];
    check("record 목록", entries.length > 0, { entries: entries.length, anchor });
    await admin.locator(`[id="${anchor}"][aria-current]`).waitFor();
    // 리포트가 가리키는 기록 위치(근거 record_ref·AI 활용 호출)가 전체 기록에 모두 있는지
    const adminJwt = await admin.evaluate(() => localStorage.getItem("dayzero.admin.token"));
    const report = (await publicApi("GET", `/admin/sessions/${sessionId}/report`, adminJwt)).body;
    const refs = new Set(entries.map((e) => `${e.ref.type}-${e.ref.id}`));
    const wanted = [
      ...report.sections.flatMap((sec) =>
        sec.cards.flatMap((c) => c.evidence.map((e) => e.record_ref).filter(Boolean)),
      ),
      ...report.rubric.elements.flatMap((el) =>
        el.cards.flatMap((c) =>
          c.items.flatMap((i) => i.evidence.map((e) => e.record_ref).filter(Boolean)),
        ),
      ),
      ...report.ai_usage.events.map((e) => ({ type: "assistant_call", id: e.call_id })),
    ];
    const lost = wanted.filter((r) => !refs.has(`${r.type}-${r.id}`));
    check("리포트 기록 링크가 전체 기록에 있음", lost.length === 0, {
      wanted: wanted.length,
      lost,
    });
    await sleep(400);
    const s1 = await shot(admin, "record");
    await admin.goto(`${WEB}/admin/positions`);
    await admin.getByText("e2e 6분 세션").click();
    await admin
      .getByText(/삭제 예정/)
      .first()
      .waitFor();
    return { shots: [s1, await shot(admin, "purge")] };
  });

  console.log("\nlog:", join(OUT, "log.json"));
} finally {
  compareShapes();
  save();
  if (process.env.KEEP !== "1") await browser.close();
}
