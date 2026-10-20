// 세션 WebSocket 연결과 재연결. 프레임 봉투와 close code는 docs/common/contracts.md의 WebSocket 절.
// 끊기면 3초 뒤 다시 붙고, 열릴 때마다 onOpen으로 알려 화면이 /state를 다시 받게 한다(WS는 증분만 보낸다).
// 4401(토큰 없음·만료)은 /s/{token}/resume으로 새 토큰을 받아 바로 다시 붙는다.
// 4000(session.replaced)·4403(다른 세션)은 다시 붙지 않는다.
import type { SendFrame, ServerFrame } from "@/components/office/types";
import { MOCK, sessionSocketUrl } from "@/lib/api";
import { createMockSocket } from "@/mocks/office";

export const RECONNECT_DELAY_MS = 3000;
export const CLOSE_REPLACED = 4000;
export const CLOSE_UNAUTHORIZED = 4401;
export const CLOSE_FORBIDDEN = 4403;

/** 브라우저 WebSocket에서 쓰는 부분만. 테스트와 mock이 같은 모양으로 갈아 끼운다. */
export type SocketLike = {
  send(data: string): void;
  close(code?: number): void;
  onopen: (() => void) | null;
  onmessage: ((event: { data: string }) => void) | null;
  onclose: ((event: { code: number }) => void) | null;
};

export type SocketFactory = (url: string) => SocketLike;

export type ConnectionStatus =
  "connecting" | "open" | "reconnecting" | "replaced" | "forbidden" | "closed";

export type SessionSocketOptions = {
  sessionId: string;
  getToken: () => string;
  /** 4401일 때 새 세션 JWT. null이면 더 붙지 않는다(세션이 끝난 경우 등) */
  refreshToken: () => Promise<string | null>;
  onFrame: (frame: ServerFrame) => void;
  onStatus: (status: ConnectionStatus) => void;
  /** 연결이 열릴 때마다. reconnected면 끊긴 사이의 상태를 /state로 따라잡아야 한다 */
  onOpen?: (info: { reconnected: boolean }) => void;
  createSocket?: SocketFactory;
};

const browserSocket: SocketFactory = (url) => new WebSocket(url) as unknown as SocketLike;

export class SessionSocket {
  private socket: SocketLike | null = null;
  private timer: ReturnType<typeof setTimeout> | null = null;
  private opened = false;
  private stopped = false;
  private isOpen = false;

  constructor(private readonly options: SessionSocketOptions) {}

  connect() {
    if (this.stopped) return;
    const { sessionId, getToken, createSocket } = this.options;
    const create = createSocket ?? (MOCK ? createMockSocket : browserSocket);
    this.options.onStatus(this.opened ? "reconnecting" : "connecting");
    const socket = create(sessionSocketUrl(sessionId, getToken()));
    this.socket = socket;
    socket.onopen = () => {
      if (socket !== this.socket) return;
      this.isOpen = true;
      const reconnected = this.opened;
      this.opened = true;
      this.options.onStatus("open");
      this.options.onOpen?.({ reconnected });
    };
    socket.onmessage = (event) => {
      if (socket !== this.socket) return;
      const frame = JSON.parse(event.data) as ServerFrame;
      this.options.onFrame(frame);
    };
    socket.onclose = (event) => {
      if (socket !== this.socket) return;
      this.isOpen = false;
      void this.closed(event.code);
    };
  }

  private async closed(code: number) {
    if (this.stopped) return;
    if (code === CLOSE_REPLACED || code === CLOSE_FORBIDDEN) {
      this.stopped = true;
      this.options.onStatus(code === CLOSE_REPLACED ? "replaced" : "forbidden");
      return;
    }
    if (code === CLOSE_UNAUTHORIZED) {
      const token = await this.options.refreshToken().catch(() => null);
      if (token === null) {
        this.stopped = true;
        this.options.onStatus("closed");
        return;
      }
      this.connect();
      return;
    }
    this.options.onStatus("reconnecting");
    this.timer = setTimeout(() => {
      this.timer = null;
      this.connect();
    }, RECONNECT_DELAY_MS);
  }

  /** 열려 있으면 보내고 true. 끊긴 동안은 false(화면은 보낼 메시지를 들고 있다가 다시 보낸다). */
  send(frame: SendFrame) {
    if (!this.socket || !this.isOpen) return false;
    this.socket.send(JSON.stringify(frame));
    return true;
  }

  close() {
    this.stopped = true;
    if (this.timer) clearTimeout(this.timer);
    this.socket?.close(1000);
    this.socket = null;
  }
}
