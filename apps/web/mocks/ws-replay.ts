// WS 이벤트 재생: 실제 소켓 대신 계약 봉투 {type, seq, payload} 프레임을 시간 순서로 흘려 보낸다.
// 기본 프레임은 계약 예시 ws_events.json(60분 한 세션)이고, at_ms가 없으면 간격 intervalMs로 보낸다.
// 15분 데모의 시각·단계 재생은 debate.ts가 debate_script.json으로 한다.
import type { ServerFrame } from "@/components/debate/types";

import events from "./fixtures/ws_events.json";

export type ReplayFrame = ServerFrame & { at_ms?: number };

/** frames를 at_ms(없으면 순번 × intervalMs) 시각에 onFrame으로 보낸다. 반환 함수로 멈춘다. */
export function replay(
  onFrame: (frame: ServerFrame) => void,
  frames: ReplayFrame[] = events as unknown as ReplayFrame[],
  intervalMs = 200,
): () => void {
  const timers = frames.map((frame, i) => {
    const { at_ms, ...rest } = frame;
    return setTimeout(() => onFrame(rest as ServerFrame), at_ms ?? i * intervalMs);
  });
  return () => timers.forEach(clearTimeout);
}
