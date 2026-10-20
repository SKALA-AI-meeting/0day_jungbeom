"use client";

// /s/[token]의 단계 전환: 링크 입장 → 안내·동의 → 대기 → 오피스 → 디브리핑.
// 단계 판정과 api 경로는 flow.ts, 오피스 상태는 reducer.ts, 연결은 lib/ws.ts에 있다.
import { useCallback, useEffect, useReducer, useRef, useState } from "react";

import { SessionSocket, type ConnectionStatus } from "@/lib/ws";

import { DebriefScreen } from "./debrief-screen";
import {
  candidateApi,
  errorCode,
  fetchSnapshot,
  land,
  landingFromError,
  LINK_NOTICES,
  partSaveHandler,
  sessionIdFromToken,
  STATE_RETRY_MS,
  submitSession,
  tokenStore,
  type CandidateApi,
} from "./flow";
import { ConsentScreen, EntryScreen, LinkNotice, WaitingScreen } from "./link-screens";
import { OfficeView } from "./office-view";
import { PartSaver } from "./part-saver";
import { initialState, reduce, type ChatChannel } from "./reducer";
import type { Debrief, Entry, ServerFrame, StateSnapshot, TaskStatus } from "./types";

type Stage =
  | { kind: "loading" }
  | { kind: "notice"; title: string; description: string; retry?: boolean }
  | { kind: "entry"; entry: Entry }
  | { kind: "consent"; entry: Entry }
  | { kind: "waiting"; entry: Entry; jwt: string }
  | { kind: "office"; entry: Entry; jwt: string; snapshot: StateSnapshot }
  | { kind: "debrief"; debrief: Debrief; revisit: boolean };

const ENDED_STATUSES = new Set(["completed", "report_ready", "approving", "reviewed", "failed"]);

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
    async (jwt: string, revisit: boolean) => {
      try {
        const debrief = await api.debrief(sessionIdFromToken(jwt), jwt);
        setStage({ kind: "debrief", debrief, revisit });
      } catch (failure) {
        // 410 expired: 종료 후 7일이 지남. 그 밖의 일시 장애는 다시 열면 볼 수 있다
        if (errorCode(failure) === "expired") {
          setStage({ kind: "notice", ...LINK_NOTICES.debrief_expired });
        } else if (revisit) {
          setStage({ kind: "notice", ...LINK_NOTICES.unknown, retry: true });
        } else {
          setStage({ kind: "notice", ...LINK_NOTICES.submitted });
        }
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
          ? showDebrief(jwt, true)
          : setStage({ kind: "notice", ...LINK_NOTICES.submitted });
      }
      // 진행 중 재입장: 저장된 JWT가 없어도 링크만으로 이어 간다
      const { session_token } = await api.resume(token);
      tokenStore.set(token, session_token);
      if (!cancelled) await enterOffice(landing.entry, session_token);
    })().catch((failure) => {
      // 재입장 중 /resume·/state 장애: 제출 완료가 아니라 연결 실패로 안내하고 다시 시도하게 한다
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
      const code = errorCode(failure);
      setError(
        code === "expired"
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
          entry={stage.entry}
          jwt={stage.jwt}
          initial={stage.snapshot}
          api={api}
          onEnded={(jwt) => showDebrief(jwt, false)}
        />
      );
    case "debrief":
      return <DebriefScreen debrief={stage.debrief} revisit={stage.revisit} />;
  }
}

function OfficeContainer({
  token,
  entry,
  jwt,
  initial,
  api,
  onEnded,
}: {
  token: string;
  entry: Entry;
  jwt: string;
  initial: StateSnapshot;
  api: CandidateApi;
  onEnded: (jwt: string) => void;
}) {
  const [state, dispatch] = useReducer(reduce, initial, (s) => initialState(s, Date.now()));
  const [now, setNow] = useState(() => Date.now());
  const [connection, setConnection] = useState<ConnectionStatus>("connecting");
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [assistantError, setAssistantError] = useState<string | null>(null);
  const jwtRef = useRef(jwt);
  const stateRef = useRef(state);
  const socketRef = useRef<SessionSocket | null>(null);
  const endedRef = useRef(false);
  /** /state 조회 중이면 그동안 도착한 프레임을 모은다(스냅샷 뒤에 다시 적용) */
  const bufferRef = useRef<ServerFrame[] | null>(null);
  const id = state.sessionId;

  useEffect(() => {
    stateRef.current = state;
  }, [state]);

  const saverRef = useRef<PartSaver | null>(null);
  useEffect(() => {
    const saver: PartSaver = new PartSaver(
      partSaveHandler({
        put: (partNo, content) => api.putPart(id, jwtRef.current, partNo, content),
        refresh: () => api.state(id, jwtRef.current),
        dispatch,
        cancel: (partNo) => saver.cancel(partNo),
      }),
    );
    saverRef.current = saver;
    return () => saver.dispose();
  }, [id, api]);

  const finish = useCallback(() => {
    if (endedRef.current) return;
    endedRef.current = true;
    socketRef.current?.close();
    onEnded(jwtRef.current);
  }, [onEnded]);

  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, []);

  useEffect(() => {
    let alive = true;
    const socket = new SessionSocket({
      sessionId: id,
      getToken: () => jwtRef.current,
      refreshToken: async () => {
        // 409 conflict면 세션이 끝났다(null → 닫힘 → 디브리핑). 일시 장애는 다시 시도한다
        while (alive) {
          try {
            const { session_token } = await api.resume(token);
            jwtRef.current = session_token;
            tokenStore.set(token, session_token);
            return session_token;
          } catch (failure) {
            if (errorCode(failure) === "conflict") return null;
            await new Promise((resolve) => setTimeout(resolve, STATE_RETRY_MS));
          }
        }
        return null;
      },
      onFrame: (frame) => {
        bufferRef.current?.push(frame);
        dispatch({ type: "frame", frame });
      },
      onStatus: (status) => {
        setConnection(status);
        if (status === "closed") finish();
      },
      onOpen: async () => {
        // WS는 증분만 보내므로 열릴 때마다 /state로 전체를 맞추고, ack 못 받은 메시지는 다시 보낸다
        // (같은 client_msg_id는 서버가 기존 메시지로 ack한다)
        // 조회 중 도착한 프레임은 스냅샷이 덮지 않게 모았다가 다시 적용한다
        const buffer: ServerFrame[] = [];
        bufferRef.current = buffer;
        const snapshot = await fetchSnapshot(
          () => api.state(id, jwtRef.current),
          () => alive && bufferRef.current === buffer,
        );
        if (bufferRef.current !== buffer) return; // 그사이 다시 연결됨
        bufferRef.current = null;
        if (snapshot) {
          dispatch({ type: "snapshot", state: snapshot, now: Date.now(), frames: buffer });
        }
        for (const out of stateRef.current.outgoing.filter((o) => !o.message_id)) {
          socket.send({
            type: "message.send",
            payload: {
              client_msg_id: out.client_msg_id,
              channel: out.channel,
              content: out.content,
            },
          });
        }
      },
    });
    socketRef.current = socket;
    socket.connect();
    return () => {
      alive = false;
      socket.close();
    };
  }, [id, token, api, finish]);

  useEffect(() => {
    if (state.ended && !submitting) finish();
  }, [state.ended, submitting, finish]);

  const onSend = (channel: ChatChannel, content: string) => {
    const client_msg_id = crypto.randomUUID();
    dispatch({ type: "send", outgoing: { client_msg_id, channel, content } });
    socketRef.current?.send({ type: "message.send", payload: { client_msg_id, channel, content } });
  };

  const onTask = (partNo: number, status: TaskStatus) => {
    dispatch({ type: "task", part_no: partNo, status });
    api.putTask(id, jwtRef.current, partNo, status).catch(async () => {
      const snapshot = await api.state(id, jwtRef.current).catch(() => null);
      if (snapshot) dispatch({ type: "snapshot", state: snapshot, now: Date.now() });
    });
  };

  const onAsk = async (prompt: string) => {
    const callId = `local-${crypto.randomUUID()}`;
    setAssistantError(null);
    dispatch({ type: "ask", call_id: callId, request: prompt });
    try {
      const reply = await api.assistant(id, jwtRef.current, prompt);
      dispatch({
        type: "answer",
        call_id: callId,
        response: reply.content,
        cited_docs: reply.cited_docs,
      });
    } catch (failure) {
      dispatch({ type: "answer", call_id: callId, response: null, cited_docs: [] });
      setAssistantError(
        errorCode(failure) === "assistant_limit"
          ? "요청 한도를 모두 사용했어요."
          : "지금은 어시스턴트를 쓸 수 없어요. 잠시 후 다시 요청해 주세요.",
      );
    }
  };

  const onSubmit = async () => {
    setSubmitting(true);
    setSubmitError(null);
    try {
      await submitSession(
        async () => saverRef.current?.flush(),
        () => api.submit(id, jwtRef.current),
        async () => {
          const snapshot = await api.state(id, jwtRef.current);
          return ENDED_STATUSES.has(snapshot.session.status);
        },
      );
      finish();
    } catch {
      // 저장 또는 제출이 실패하면 오피스와 원고를 그대로 두고 다시 시도하게 한다
      setSubmitError(
        "저장하지 못한 내용이 있어 제출하지 못했어요. 연결을 확인하고 다시 제출해 주세요.",
      );
      setSubmitting(false);
    }
  };

  return (
    <OfficeView
      state={state}
      companyName={entry.company_name}
      now={now}
      connection={connection}
      submitting={submitting}
      submitError={submitError}
      assistantError={assistantError}
      onView={(channel) => dispatch({ type: "view", channel })}
      onSend={onSend}
      onEdit={(partNo, content) => {
        dispatch({ type: "edit", part_no: partNo, content });
        saverRef.current?.schedule(partNo, content);
      }}
      onRetrySave={(partNo) => void saverRef.current?.retry(partNo).catch(() => {})}
      onTask={onTask}
      onOpenDoc={async (docId) => {
        const doc = await api.document(id, jwtRef.current, docId);
        dispatch({ type: "opened", doc_id: docId });
        return doc;
      }}
      onAsk={onAsk}
      onSubmit={onSubmit}
      onDismissNotice={(noticeId) => dispatch({ type: "dismiss_notice", id: noticeId })}
    />
  );
}
