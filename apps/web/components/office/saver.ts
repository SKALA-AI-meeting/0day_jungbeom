// 문서별 디바운스 저장. 같은 문서의 저장은 한 번에 하나씩(직렬) 돌고, flush는 예약·진행 중인 저장이 끝날 때까지
// 기다려 마지막 저장이 성공했는지 돌려준다. 제출·공유·가져오기는 flush가 false면 멈춘다(서버에 옛 본문이 남지 않게).
// job은 실행 시점의 최신 본문을 읽어 저장하고, 실패하면 throw 한다.

type Slot = {
  timer: ReturnType<typeof setTimeout> | null;
  job: () => Promise<void>;
  running: Promise<void> | null;
  ok: boolean;
};

export function createSaver(delayMs: number) {
  const slots = new Map<string, Slot>();
  let stopped = false;

  const run = (key: string, slot: Slot) => {
    const previous = slot.running ?? Promise.resolve();
    const current = previous.then(async () => {
      if (stopped) return;
      try {
        await slot.job();
        slot.ok = true;
      } catch {
        slot.ok = false;
      }
    });
    slot.running = current;
    void current.then(() => {
      if (slots.get(key)?.running === current) slot.running = null;
    });
    return current;
  };

  return {
    /** delayMs 뒤 저장. 그 사이 다시 부르면 타이머를 새로 잡는다 */
    schedule(key: string, job: () => Promise<void>) {
      if (stopped) return;
      const slot = slots.get(key) ?? { timer: null, job, running: null, ok: true };
      slot.job = job;
      if (slot.timer) clearTimeout(slot.timer);
      slot.timer = setTimeout(() => {
        slot.timer = null;
        void run(key, slot);
      }, delayMs);
      slots.set(key, slot);
    },
    /**
     * key(없으면 전부)의 예약 저장을 바로 돌리고 끝까지 기다린다. 직전 저장이 실패했으면 다시 시도한다.
     * 기다리는 사이 새 편집이 예약되면 그것까지 비울 때까지 반복한다. 기다리는 사이 멈췄으면(stop) false.
     */
    async flush(key?: string): Promise<boolean> {
      const targets = () => [...slots.entries()].filter(([k]) => key === undefined || k === key);
      let retried = new Set<string>();
      for (;;) {
        if (stopped) return false;
        const work = targets().flatMap(([k, slot]) => {
          if (slot.timer || (!slot.ok && !retried.has(k))) {
            if (slot.timer) clearTimeout(slot.timer);
            slot.timer = null;
            retried.add(k);
            return [run(k, slot)];
          }
          return slot.running ? [slot.running] : [];
        });
        if (work.length === 0) break;
        await Promise.all(work);
        // 다음 바퀴: 기다리는 동안 새로 예약된 편집만 다시 시도 대상이 된다
        retried = new Set([...retried].filter((k) => !slots.get(k)?.timer));
      }
      return !stopped && targets().every(([, slot]) => slot.ok);
    },
    /** 접속 교체 등으로 이 창이 멈추면 예약 저장을 버리고 새 저장도 받지 않는다 */
    stop() {
      stopped = true;
      for (const slot of slots.values()) if (slot.timer) clearTimeout(slot.timer);
    },
  };
}

export type Saver = ReturnType<typeof createSaver>;
