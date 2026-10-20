"use client";

// 개발용 mock 조작 패널(NEXT_PUBLIC_MOCK=1에서만 보인다). 장면 진행·시간 이동·연결 끊기로 오피스 상태를 만든다.
// 조작 뒤에는 /state를 다시 받아 시계(ends_at)와 화면을 맞춘다.
import { useState } from "react";

import { cn } from "@/components/ui";
import { setWorst, useWorst } from "@/components/dev/data-toggle";
import { mockControls, SESSION_MINUTES } from "@/mocks/office";

export function MockControls({ sessionId, onResync }: { sessionId: string; onResync: () => void }) {
  const [openPanel, setOpenPanel] = useState(false);
  const [, setTick] = useState(0);
  const worst = useWorst();
  const controls = mockControls(sessionId);
  const act = (job: () => void) => {
    job();
    setTick((n) => n + 1);
    setTimeout(onResync, 80);
  };
  const button = "rounded px-2 py-1 text-left text-xs hover:bg-surface-sunken disabled:opacity-40";
  const running = controls.status() === "in_progress";
  return (
    <div className="rounded-md border border-dashed border-subtle bg-surface/70 text-xs">
      <button
        type="button"
        onClick={() => setOpenPanel((v) => !v)}
        className="flex w-full items-center justify-between px-2.5 py-1.5 font-mono text-subtle"
      >
        mock 조작 <span>{openPanel ? "▾" : "▸"}</span>
      </button>
      {openPanel && (
        <div className="flex flex-col gap-0.5 border-t border-dashed border-subtle p-1.5">
          <button type="button" className={button} onClick={() => setWorst(!worst)}>
            데이터: {worst ? "Worst case → Demo로" : "Demo → Worst case로"}
          </button>
          <p className="px-2 pb-1 text-subtle tabular-nums">
            세션 {controls.now().toFixed(1)}분 · {controls.status()}
          </p>
          {controls.scenes().map((scene) => (
            <span
              key={scene.id}
              className={cn("px-2", scene.fired ? "text-subtle line-through" : "text-ink")}
            >
              {scene.at_min}분 {scene.label}
            </span>
          ))}
          <button
            type="button"
            disabled={!running}
            className={cn(button, "font-semibold text-accent")}
            onClick={() => act(controls.nextScene)}
          >
            다음 장면 ▶
          </button>
          <button
            type="button"
            disabled={!running}
            className={button}
            onClick={() => act(() => controls.jumpTo(SESSION_MINUTES - 2.1))}
          >
            마감 2분 전으로
          </button>
          <button
            type="button"
            disabled={!running}
            className={button}
            onClick={() => act(() => controls.jumpTo(SESSION_MINUTES))}
          >
            시간 만료(자동 제출)
          </button>
          <button type="button" className={button} onClick={() => act(() => controls.drop())}>
            연결 끊기(3초 뒤 재연결)
          </button>
          <button type="button" className={button} onClick={() => act(() => controls.drop(4000))}>
            다른 창에서 접속
          </button>
          <button
            type="button"
            disabled={controls.status() !== "reporting"}
            className={button}
            onClick={() => act(controls.passDeadline)}
          >
            보고 5분 지나기
          </button>
        </div>
      )}
    </div>
  );
}
