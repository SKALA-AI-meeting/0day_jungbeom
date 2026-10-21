"use client";

// /s/[token]의 단계 전환: 링크 입장 → 안내·동의 → 대기 → 오피스(보고 대기 포함) → 디브리핑.
// 단계 판정과 api 경로는 flow.ts, 오피스 상태는 reducer.ts, 연결은 lib/ws.ts에 있다.
import { useCallback, useEffect, useReducer, useRef, useState } from "react";

import { Toaster, toast } from "@/components/ui";
import { MOCK } from "@/lib/api";
import { SessionSocket, type ConnectionStatus } from "@/lib/ws";

import { DebriefScreen } from "./debrief-screen";
import { createSaver } from "./saver";
import {
  candidateApi,
  errorCode,
  errorText,
  fetchSnapshot,
  land,
  landingFromError,
  LINK_NOTICES,
  sessionIdFromToken,
  tokenStore,
  type CandidateApi,
} from "./flow";
import { DEADLINE_10, DEADLINE_2, personName } from "./lines";
import { ConsentScreen, EntryScreen, LinkNotice, WaitingScreen } from "./link-screens";
import { MockControls } from "./mock-controls";
import { OfficeView, type OfficeHandle } from "./office-view";
import type { SaveState } from "./my-docs";
import { boardLineFor, firstLine, initialState, nowMin, reduce, shouldToast } from "./reducer";
import type { Channel, Debrief, Entry, ServerFrame, StateSnapshot, Task } from "./types";

type Stage =
  | { kind: "loading" }
  | { kind: "notice"; title: string; description: string; retry?: boolean }
  | { kind: "entry"; entry: Entry }
  | { kind: "consent"; entry: Entry }
  | { kind: "waiting"; entry: Entry; jwt: string }
  | { kind: "office"; entry: Entry; jwt: string; snapshot: StateSnapshot }
  | { kind: "debrief"; debrief: Debrief; jwt: string; revisit: boolean; contact?: string };

/** 오피스 화면에서 보이는 지원자 별칭. State의 session.alias가 정본이고, 없으면 킥오프 문장에서 읽는다 */
function aliasOf(snapshot: StateSnapshot) {
  if (snapshot.session.alias) return snapshot.session.alias;
  const kickoff = snapshot.messages.find((m) => m.sender === "manager")?.content ?? "";
  return /주담당은 (.+?)님입니다/.exec(kickoff)?.[1] ?? "나";
}

export function CandidateFlow({
  token,
  api = candidateApi,
}: {
  token: string;
  api?: CandidateApi;
}) {
  const [stage, setStage] = useState<Stage>({ kind: "loading" });
  const [agreed, setAgreed] = useState(false);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);

  const showDebrief = useCallback(
    async (jwt: string, revisit: boolean, contact?: string) => {
      try {
        const debrief = await api.debrief(sessionIdFromToken(jwt), jwt);
        setStage({ kind: "debrief", debrief, jwt, revisit, contact });
      } catch (failure) {
        // 410 expired: 종료 후 7일이 지남. 그 밖의 일시 장애는 다시 열면 볼 수 있다
        if (errorCode(failure) === "expired")
          setStage({ kind: "notice", ...LINK_NOTICES.debrief_expired });
        else if (revisit) setStage({ kind: "notice", ...LINK_NOTICES.unknown, retry: true });
        else setStage({ kind: "notice", ...LINK_NOTICES.submitted });
      }
    },
    [api],
  );

  const enterOffice = useCallback(
    async (entry: Entry, jwt: string) => {
      const snapshot = await api.state(sessionIdFromToken(jwt), jwt);
      setStage({ kind: "office", entry, jwt, snapshot });
    },
    [api],
  );

  useEffect(() => {
    let cancelled = false;
    (async () => {
      const landing = await land(token);
      if (cancelled) return;
      if (landing.kind === "notice") return setStage(landing);
      if (landing.kind === "entry") return setStage({ kind: "entry", entry: landing.entry });
      if (landing.kind === "ended") {
        const jwt = landing.entry.debrief_token;
        return jwt
          ? showDebrief(jwt, true, landing.entry.contact_email)
          : setStage({ kind: "notice", ...LINK_NOTICES.submitted });
      }
      // 진행 중·보고 대기 재입장: 저장된 JWT가 없어도 링크만으로 이어 간다
      const { session_token } = await api.resume(token);
      tokenStore.set(token, session_token);
      if (!cancelled) await enterOffice(landing.entry, session_token);
    })().catch((failure) => {
      // 재입장 중 /resume·/state 장애는 제출 완료가 아니라 연결 실패로 안내하고 다시 시도하게 한다
      if (!cancelled) setStage(landingFromError(failure));
    });
    return () => {
      cancelled = true;
    };
  }, [token, api, enterOffice, showDebrief, attempt]);

  const run = async (job: () => Promise<void>) => {
    setPending(true);
    setError(null);
    try {
      await job();
    } catch (failure) {
      setError(
        errorCode(failure) === "expired"
          ? "링크가 만료되었습니다. 채용 담당자에게 문의해 주세요."
          : "잠시 후 다시 시도해 주세요.",
      );
    } finally {
      setPending(false);
    }
  };

  switch (stage.kind) {
    case "loading":
      return <p className="p-10 text-center text-muted">불러오는 중…</p>;
    case "notice":
      return (
        <LinkNotice
          title={stage.title}
          description={stage.description}
          onRetry={
            stage.retry
              ? () => {
                  setStage({ kind: "loading" });
                  setAttempt((n) => n + 1);
                }
              : undefined
          }
        />
      );
    case "entry":
      return (
        <EntryScreen
          entry={stage.entry}
          onNext={() => setStage({ kind: "consent", entry: stage.entry })}
        />
      );
    case "consent":
      return (
        <ConsentScreen
          entry={stage.entry}
          agreed={agreed}
          onAgreedChange={setAgreed}
          pending={pending}
          error={error}
          onConsent={() =>
            run(async () => {
              if (!agreed) return;
              const { session_token } = await api.consent(token);
              tokenStore.set(token, session_token);
              setStage({ kind: "waiting", entry: stage.entry, jwt: session_token });
            })
          }
        />
      );
    case "waiting":
      return (
        <WaitingScreen
          entry={stage.entry}
          pending={pending}
          error={error}
          onStart={() =>
            run(async () => {
              await api.start(token, stage.jwt);
              await enterOffice(stage.entry, stage.jwt);
            })
          }
        />
      );
    case "office":
      return (
        <OfficeContainer
          token={token}
          jwt={stage.jwt}
          initial={stage.snapshot}
          api={api}
          onEnded={(jwt) => showDebrief(jwt, false)}
          onLost={() => {
            setStage({ kind: "loading" });
            setAttempt((n) => n + 1);
          }}
        />
      );
    case "debrief":
      return (
        <DebriefScreen
          debrief={stage.debrief}
          revisit={stage.revisit}
          contactEmail={stage.contact}
          onSurvey={async (answers) => {
            await api.survey(sessionIdFromToken(stage.jwt), stage.jwt, answers);
          }}
        />
      );
  }
}

const SAVE_DELAY_MS = 1000;

/** resume이 "세션이 끝나 더 이을 수 없음"으로 거절했는지(409 conflict·410 expired/cancelled·404) */
function isTerminal(failure: unknown) {
  const status = (failure as { status?: unknown } | null)?.status;
  return status === 409 || status === 410 || status === 404;
}
const ENDED_DELAY_MS = 1500;

function OfficeContainer({
  token,
  jwt: initialJwt,
  initial,
  api,
  onEnded,
  onLost,
}: {
  token: string;
  jwt: string;
  initial: StateSnapshot;
  api: CandidateApi;
  onEnded: (jwt: string) => void;
  /** 연결을 더 이을 수 없음(세션 JWT를 다시 받지 못함) */
  onLost: () => void;
}) {
  const [state, dispatch] = useReducer(reduce, initial, initialState);
  const [connection, setConnection] = useState<ConnectionStatus>("connecting");
  const [now, setNow] = useState(() => Date.now());
  const [saves, setSaves] = useState<Record<string, SaveState>>({});
  const [taskErrors, setTaskErrors] = useState<Record<number, string>>({});
  const [assistantPending, setAssistantPending] = useState<string | null>(null);
  const [assistantError, setAssistantError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const id = initial.session.id;
  const jwt = useRef(initialJwt);
  const socket = useRef<SessionSocket | null>(null);
  const stateRef = useRef(state);
  const editing = useRef({ editing: false, docOpen: false });
  const office = useRef<OfficeHandle>(null);
  const [saver] = useState(() => createSaver(SAVE_DELAY_MS));
  const msgSeq = useRef(0);
  const alias = aliasOf(initial);

  // 부모가 렌더마다 새로 만드는 콜백이라 소켓 effect가 다시 돌지 않게 ref로 읽는다
  const lost = useRef(onLost);
  useEffect(() => {
    stateRef.current = state;
    lost.current = onLost;
  });

  // 조회 중에 온 프레임은 모아 두었다가 스냅샷 뒤에 다시 얹는다(스냅샷이 그 프레임보다 먼저 만들어졌을 수 있다)
  const during = useRef<ServerFrame[] | null>(null);
  const mounted = useRef(true);
  const refreshing = useRef({ running: false, again: false });
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
      // 화면을 떠나면 남은 예약 저장을 버린다(옛 JWT로 돌지 않게). 개발 모드의 즉시 재마운트는 건너뛴다
      setTimeout(() => {
        if (!mounted.current) saver.stop();
      }, 0);
    };
  }, [saver]);
  // 재동기화는 한 번에 하나만 돈다. 도는 중에 다시 불리면 끝난 뒤 한 번 더 받아 최신 상태로 맞춘다.
  // 화면을 떠나면(언마운트) 재시도를 멈춘다
  const refresh = useCallback(async () => {
    const r = refreshing.current;
    if (r.running) {
      r.again = true;
      return;
    }
    r.running = true;
    do {
      r.again = false;
      during.current = [];
      // 조회 시작 시점의 저장 세대. 이보다 뒤에 성공한 저장은 응답보다 최신이다
      const since = stateRef.current.saveSeq;
      const snapshot = await fetchSnapshot(
        () => api.state(id, jwt.current),
        () => mounted.current,
      );
      const frames = during.current ?? [];
      during.current = null;
      if (snapshot) dispatch({ type: "snapshot", state: snapshot, frames, since });
    } while (mounted.current && r.again);
    r.running = false;
  }, [api, id]);

  const sendFrame = (p: {
    client_msg_id: string;
    channel: "team" | "dm" | "manager_dm";
    content: string;
    reply_to_doc?: { doc_id: string; version: number };
  }) => socket.current?.send({ type: "message.send", payload: p }) ?? false;

  useEffect(() => {
    const s = new SessionSocket({
      sessionId: id,
      getToken: () => jwt.current,
      refreshToken: async () => {
        // 4401: 링크로 새 세션 JWT를 받는다. 세션이 끝났다는 응답(409·410·404)만 null로 멈추고,
        // 네트워크·5xx는 throw 해 소켓이 재발급을 다시 시도한다(오피스와 미저장 편집은 그대로 둔다)
        try {
          const { session_token } = await api.resume(token);
          jwt.current = session_token;
          tokenStore.set(token, session_token);
          return session_token;
        } catch (failure) {
          if (isTerminal(failure)) return null;
          throw failure;
        }
      },
      onStatus: (status) => {
        setConnection(status);
        // 다른 창으로 옮겨 갔거나 접속이 거절되면 이 창의 쓰기를 모두 멈춘다
        if (status === "replaced" || status === "forbidden") {
          saver.stop();
          dispatch({ type: "stopped" });
        }
        // 4401 뒤 resume이 종료 응답으로 거절됨(끊긴 사이 세션이 끝남): 링크 입장부터 다시 판정해 디브리핑으로 보낸다
        if (status === "closed") lost.current();
      },
      onOpen: ({ reconnected }) => {
        // 첫 연결도 따라잡는다: 입장 때 받은 /state와 WS가 열리기 사이의 변화는 프레임으로 오지 않는다
        void refresh();
        if (reconnected) toast("연결이 다시 이어졌어요");
        // 끊긴 동안 쌓인 메시지는 같은 client_msg_id로 다시 보낸다(서버가 중복을 막는다)
        for (const p of stateRef.current.pending) sendFrame(p);
      },
      onFrame: (frame: ServerFrame) => {
        if (frame.type === "session.replaced") saver.stop();
        dispatch({ type: "frame", frame });
        during.current?.push(frame);
        if (frame.type === "message.new") {
          const m = frame.payload;
          if (shouldToast(m, { ...editing.current, channel: stateRef.current.channel })) {
            const who =
              m.channel === "notice"
                ? "리서치 담당"
                : personName(m.sender, stateRef.current.snap.persona);
            toast(who, {
              description: firstLine(m.content),
              action: {
                label: "보기",
                // 대화 탭 전환·뷰어 닫기까지 화면이 맡는다(채널 값이 같아도 대화로 이동)
                onClick: () =>
                  office.current
                    ? office.current.showChannel(m.channel)
                    : dispatch({ type: "view", channel: m.channel }),
              },
            });
          }
        }
      },
    });
    socket.current = s;
    s.connect();
    return () => s.close();
    // sendFrame은 socket.current만 읽는다. saver는 마운트 동안 같은 객체다
  }, [api, id, token, refresh, saver]);

  // 끝나면 잠깐 안내를 보인 뒤 디브리핑으로 넘어간다
  useEffect(() => {
    if (!state.ended) return;
    const t = setTimeout(() => onEnded(jwt.current), ENDED_DELAY_MS);
    return () => clearTimeout(t);
  }, [state.ended, onEnded]);

  // 시계: 마감 10분·2분 전 줄(2분 전은 토스트도)
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(t);
  }, []);
  const endsAt = state.snap.session.ends_at ? Date.parse(state.snap.session.ends_at) : null;
  const remaining = endsAt == null ? null : (endsAt - now) / 1000;
  const inProgress = state.snap.session.status === "in_progress";
  useEffect(() => {
    if (!inProgress || remaining == null || remaining <= 0) return;
    const at = nowMin(stateRef.current.snap, now);
    if (remaining <= 600 && !stateRef.current.lines.some((l) => l.id === "deadline-10")) {
      dispatch({
        type: "line",
        line: { id: "deadline-10", channel: "all", t_min: at, kind: "deadline", text: DEADLINE_10 },
      });
    }
    if (remaining <= 120 && !stateRef.current.lines.some((l) => l.id === "deadline-2")) {
      dispatch({
        type: "line",
        line: { id: "deadline-2", channel: "all", t_min: at, kind: "deadline", text: DEADLINE_2 },
      });
      toast.warning(DEADLINE_2);
    }
  }, [inProgress, remaining, now]);

  /** 서버 거절 문구. 제출 뒤 저장은 409 session_ending */
  const failText = (failure: unknown, fallback: string) =>
    errorCode(failure) === "session_ending"
      ? "제출한 뒤라 반영되지 않았어요."
      : (errorText(failure) ?? fallback);

  // 1초 디바운스 저장(문서별 직렬). 제출·공유·가져오기 전에는 flush로 저장 성공을 확인한다
  const schedule = (key: string, job: () => Promise<void>) => {
    if (stateRef.current.replaced) return;
    saver.schedule(key, job);
    // 해결되지 않은 실패는 다시 저장하는 동안에도 남기고, 성공 응답(saved)에서만 지운다
    setSaves((s) => ({ ...s, [key]: s[key] === "failed" ? "failed" : "saving" }));
  };
  /** 저장이 끝나지 않았으면 다음 동작을 멈추고 알린다 */
  const ensureSaved = async (key: string | undefined, action: string) => {
    const ok = await saver.flush(key);
    // 기다리는 사이 다른 창으로 옮겨 갔으면 이 창에서는 더 쓰지 않는다
    if (stateRef.current.replaced) return false;
    if (ok) return true;
    toast.error(`저장되지 않아 ${action}을(를) 멈췄어요. 연결을 확인하고 다시 시도해 주세요.`);
    return false;
  };

  // 저장 작업은 실행 시점의 최신 본문을 읽고, 실패하면 throw 해 saver가 실패로 기록한다
  const saveDoc = (partNo: number) => async () => {
    const doc = stateRef.current.snap.my_documents.find((d) => d.part_no === partNo);
    if (!doc) return;
    const content = doc.content;
    try {
      const saved = await api.saveDoc(id, jwt.current, partNo, content);
      dispatch({
        type: "doc_saved",
        part_no: partNo,
        content,
        revision: saved.revision,
        updated_at: saved.updated_at,
      });
      setSaves((s) => ({ ...s, [partNo]: "saved" }));
    } catch (failure) {
      setSaves((s) => ({ ...s, [partNo]: "failed" }));
      toast.error(failText(failure, "저장하지 못했어요. 잠시 후 다시 시도합니다."));
      throw failure;
    }
  };

  const saveFinal = async () => {
    const sections = stateRef.current.snap.final.sections.map(({ part_no, content }) => ({
      part_no,
      content,
    }));
    try {
      await api.saveFinal(id, jwt.current, sections);
      dispatch({ type: "final_saved", sections });
      setSaves((s) => ({ ...s, final: "saved" }));
    } catch (failure) {
      setSaves((s) => ({ ...s, final: "failed" }));
      toast.error(failText(failure, "최종본을 저장하지 못했어요."));
      throw failure;
    }
  };

  const onTask = async (partNo: number, patch: Partial<Task>) => {
    if (stateRef.current.replaced) return;
    const before = stateRef.current.snap.tasks.find((t) => t.part_no === partNo);
    if (!before) return;
    dispatch({ type: "task_local", task: { ...before, ...patch } });
    try {
      await api.putTask(id, jwt.current, partNo, patch);
      const line = boardLineFor(stateRef.current, before, { ...before, ...patch });
      if (line) dispatch({ type: "line", line });
      setTaskErrors((e) => {
        const next = { ...e };
        delete next[partNo];
        return next;
      });
    } catch (failure) {
      // 422 invalid_division은 조건 문장을 카드 상세에 그대로 보여 주고 서버 값으로 되돌린다
      dispatch({ type: "task_local", task: before });
      setTaskErrors((e) => ({ ...e, [partNo]: failText(failure, "보드를 바꾸지 못했어요.") }));
    }
  };

  const onEditingChange = useCallback((value: { editing: boolean; docOpen: boolean }) => {
    editing.current = value;
  }, []);

  return (
    <>
      <OfficeView
        ref={office}
        state={state}
        alias={alias}
        now={now}
        connection={connection}
        saves={saves}
        taskErrors={taskErrors}
        assistantPending={assistantPending}
        assistantError={assistantError}
        submitting={submitting}
        devSlot={MOCK ? <MockControls sessionId={id} onResync={() => void refresh()} /> : null}
        onEditingChange={onEditingChange}
        onView={(channel: Channel) => dispatch({ type: "view", channel })}
        onSend={(channel, content, reply) => {
          msgSeq.current += 1;
          const p = {
            client_msg_id: `c-${Date.now()}-${msgSeq.current}`,
            channel,
            content,
            ...(reply ? { reply_to_doc: reply } : {}),
          };
          dispatch({ type: "sending", pending: { ...p, t_min: nowMin(stateRef.current.snap) } });
          sendFrame(p);
        }}
        onOpenDoc={async (ref) => {
          const opened = await api.open(id, jwt.current, ref.doc_id, ref.version);
          dispatch({ type: "opened", doc_id: ref.doc_id, version: ref.version });
          return opened.content;
        }}
        onImport={async (partNo, source) => {
          // 최종본과 가져올 내 문서 원본의 예약 저장을 먼저 끝낸다(원본의 옛 저장본을 가져오지 않게)
          const mine = stateRef.current.snap.my_documents.find(
            (d) => d.doc_id === source.source_doc_id,
          );
          if (!(await ensureSaved("final", "가져오기"))) return;
          if (mine && !(await ensureSaved(String(mine.part_no), "가져오기"))) return;
          try {
            const section = await api.importSection(id, jwt.current, partNo, source);
            dispatch({ type: "final_section", section });
            toast(`최종본 ${partNo}번 섹션에 가져왔어요`);
          } catch (failure) {
            toast.error(failText(failure, "가져오지 못했어요."));
          }
        }}
        onEditDoc={(partNo, content) => {
          dispatch({ type: "doc_edit", part_no: partNo, content });
          schedule(String(partNo), saveDoc(partNo));
        }}
        onShare={async (partNo, channel, note) => {
          if (!(await ensureSaved(String(partNo), "보내기"))) return;
          try {
            const shared = await api.share(id, jwt.current, partNo, channel, note);
            dispatch({
              type: "shared",
              part_no: partNo,
              version: shared.version,
              message_id: shared.message_id,
              channel,
              t_min: nowMin(stateRef.current.snap),
            });
            toast(
              `${partNo}번 v${shared.version}을(를) ${channel === "team" ? "팀 채널" : "도현님 DM"}에 보냈어요`,
            );
          } catch (failure) {
            toast.error(failText(failure, "보내지 못했어요."));
          }
        }}
        onEditFinal={(partNo, content) => {
          dispatch({ type: "final_edit", part_no: partNo, content });
          schedule("final", saveFinal);
        }}
        onSubmit={async () => {
          setSubmitting(true);
          // 제출 준비부터 편집을 잠가 저장을 비우는 사이 새 입력이 생기지 않게 한다
          dispatch({ type: "submitting", on: true });
          if (!(await ensureSaved(undefined, "제출"))) {
            if (!stateRef.current.replaced) dispatch({ type: "submitting", on: false });
            setSubmitting(false);
            return;
          }
          try {
            const result = await api.submit(id, jwt.current);
            dispatch({
              type: "submitted",
              status: result.status,
              deadline_at: result.deadline_at ?? null,
            });
          } catch (failure) {
            dispatch({ type: "submitting", on: false });
            toast.error(failText(failure, "제출하지 못했어요. 다시 시도해 주세요."));
          } finally {
            setSubmitting(false);
          }
        }}
        onTask={(partNo, patch) => void onTask(partNo, patch)}
        onMove={async (patches) => {
          for (const { part_no, ...patch } of patches) await onTask(part_no, patch);
        }}
        onReadCompany={async (docId) => (await api.document(id, jwt.current, docId)).content}
        onAsk={async (prompt) => {
          setAssistantPending(prompt);
          setAssistantError(null);
          try {
            const reply = await api.assistant(id, jwt.current, prompt);
            dispatch({
              type: "assistant",
              call: {
                call_id: reply.call_id,
                request: prompt,
                response: reply.content,
                cited_docs: reply.cited_docs,
                t_min: nowMin(stateRef.current.snap),
              },
            });
          } catch (failure) {
            setAssistantError(
              errorCode(failure) === "assistant_limit"
                ? "이번 세션의 어시스턴트 요청 한도(60회)를 다 썼어요."
                : failText(failure, "응답을 받지 못했어요. 다시 시도해 주세요."),
            );
          } finally {
            setAssistantPending(null);
          }
        }}
      />
      <Toaster />
    </>
  );
}
