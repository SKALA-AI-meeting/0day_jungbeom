// 기획안 파트 저장: 마지막 입력 1초 뒤 PUT. 파트마다 따로 기다리고, 제출 전 flush()로 남은 것을 끝낸다.
// 같은 파트는 한 번에 하나만 보내고, 보내는 동안 바뀐 본문은 끝난 뒤 최신 것 하나만 이어 보낸다.
// save가 실패(throw)하면 최신 본문을 그대로 들고 있다가 다음 입력·retry·flush 때 다시 보낸다.
// 권한 거부(403)처럼 다시 보내도 소용없는 경우는 save가 직접 처리하고 정상 반환하며 cancel()로 남은 본문을 버린다.

export type SaveFn = (partNo: number, content: string) => Promise<void>;

export const SAVE_DELAY_MS = 1000;

export class PartSaver {
  private timers = new Map<number, ReturnType<typeof setTimeout>>();
  /** 아직 서버에 저장되지 않은 최신 본문 */
  private latest = new Map<number, string>();
  private running = new Map<number, Promise<void>>();

  constructor(
    private readonly save: SaveFn,
    private readonly delay = SAVE_DELAY_MS,
  ) {}

  schedule(partNo: number, content: string) {
    this.latest.set(partNo, content);
    clearTimeout(this.timers.get(partNo));
    this.timers.set(
      partNo,
      // 실패는 save 쪽에서 화면에 알렸다. 여기서는 처리되지 않은 거부만 막는다
      setTimeout(() => this.run(partNo).catch(() => {}), this.delay),
    );
  }

  /** 기다리지 않고 지금 보낸다(“다시 시도”). */
  retry(partNo: number) {
    clearTimeout(this.timers.get(partNo));
    this.timers.delete(partNo);
    return this.run(partNo);
  }

  /** 이 파트의 예약과 저장 안 된 본문을 버린다(권한 거부 등). */
  cancel(partNo: number) {
    clearTimeout(this.timers.get(partNo));
    this.timers.delete(partNo);
    this.latest.delete(partNo);
  }

  private run(partNo: number): Promise<void> {
    this.timers.delete(partNo);
    const current = this.running.get(partNo);
    if (current) return current.then(() => this.run(partNo));
    if (!this.latest.has(partNo)) return Promise.resolve();
    const job = this.pump(partNo).finally(() => this.running.delete(partNo));
    this.running.set(partNo, job);
    return job;
  }

  private async pump(partNo: number) {
    while (this.latest.has(partNo)) {
      const content = this.latest.get(partNo)!;
      await this.save(partNo, content);
      // 저장하는 사이 새 입력이 없을 때만 비운다
      if (this.latest.get(partNo) === content) this.latest.delete(partNo);
    }
  }

  /** 기다리는 저장을 지금 보내고 모두 저장(또는 권한 거부 처리)될 때까지 기다린다. 하나라도 실패하면 거부한다. */
  async flush() {
    const parts = new Set([...this.timers.keys(), ...this.latest.keys(), ...this.running.keys()]);
    parts.forEach((partNo) => clearTimeout(this.timers.get(partNo)));
    await Promise.all([...parts].map((partNo) => this.run(partNo)));
    // 기다리는 사이 들어온 입력도 끝낸다
    if (this.latest.size > 0) await this.flush();
  }

  dispose() {
    this.timers.forEach(clearTimeout);
    this.timers.clear();
  }
}
