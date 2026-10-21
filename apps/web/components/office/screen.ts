// 메인 탭 화면 규칙(CX-08): 채널로 이동할 때의 탭·문서 뷰어, [대화] 탭 배지 수. 화면 상태 없이 계산만 한다.
import type { MainTab } from "./main-tabs";
import { isSystemLine } from "./reducer";
import type { Channel, Message } from "./types";

/** 동료·팀장·알림이 보낸 메시지 수(내 메시지·시스템 줄 제외). channel을 주면 그 채널만 센다 */
export function othersCount(messages: Message[], channel?: Channel) {
  return messages.filter(
    (m) =>
      (channel == null || m.channel === channel) && m.sender !== "candidate" && !isSystemLine(m),
  ).length;
}

/**
 * 레일·토스트의 "보기"·답글로 채널을 고를 때: 채널 값이 같아도 항상 대화 탭으로 오고,
 * 열린 받은 문서 뷰어는 닫는다(뷰어가 새 메시지를 가리지 않게).
 */
export function showChannel<D>(screen: { tab: MainTab; open: D | null }) {
  return { ...screen, tab: "chat" as MainTab, open: null };
}

/**
 * [대화] 탭 배지: 대화가 아닌 탭에 있는 동안 도착한 새 메시지 수(채널 구분 없음).
 * seen은 마지막으로 대화 탭을 보던 때의 othersCount(전체)다. 대화 탭에서는 0.
 */
export function chatBadge(total: number, seen: number, tab: MainTab) {
  return tab === "chat" ? 0 : Math.max(0, total - seen);
}
