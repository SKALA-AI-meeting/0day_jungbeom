// WS 이벤트 재생: 실제 소켓 대신 프레임을 시간 순서로 흘려 보낸다. 프레임 형식은 api hub와 같다.
import events from "./fixtures/ws_events.json";

export type ReplayFrame = { at_ms: number; type: string; payload: Record<string, unknown> };

/** frames를 at_ms 시각에 onFrame으로 보낸다. speed 2면 두 배 빠르게. 반환 함수로 멈춘다. */
export function replay(
  onFrame: (frame: { type: string; payload: Record<string, unknown> }) => void,
  frames: ReplayFrame[] = events as ReplayFrame[],
  speed = 1,
): () => void {
  const timers = frames.map((frame) =>
    setTimeout(() => onFrame({ type: frame.type, payload: frame.payload }), frame.at_ms / speed),
  );
  return () => timers.forEach(clearTimeout);
}
