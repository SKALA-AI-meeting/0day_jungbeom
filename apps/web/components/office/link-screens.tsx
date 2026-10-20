"use client";

// 오피스에 들어가기 전 화면: 링크 안내(만료·취소·없음), 입장 안내, 동의, 대기. 문구는 docs/frontend/design.md.
import type { ReactNode } from "react";

import { Avatar, Button, Wordmark } from "@/components/ui";

import type { Entry } from "./types";

export const DOC_FLOW_LINE =
  "각자 파트 문서 작성·보내기 → 받은 문서 열기·답글 → 주담당이 최종본으로 합쳐 제출";
export const PRIMARY_ROLE_LINE =
  "주담당: 같은 팀원이면서 이번 건을 이끄는 사람. 파트 나누기, 최종본 합치기, 마감 보고.";
/** 오피스에서 할 일 순서(도움말·대기 화면) */
export const WORK_STEPS = [
  "보드에서 카드 5장 담당 정하기(분업)",
  "내 파트 문서 쓰고 보내기, 받은 문서 열고 답글",
  "★ 최종본으로 합쳐 제출, 팀장에게 보고",
];

function Page({ children, width = "max-w-xl" }: { children: ReactNode; width?: string }) {
  return (
    <main className={`mx-auto flex min-h-dvh ${width} flex-col justify-center gap-6 px-6 py-16`}>
      <Wordmark className="h-5 self-start" />
      {children}
    </main>
  );
}

export function LinkNotice({
  title,
  description,
  onRetry,
}: {
  title: string;
  description: string;
  onRetry?: () => void;
}) {
  return (
    <Page>
      <h1 className="text-2xl font-semibold">{title}</h1>
      <p className="text-muted">{description}</p>
      {onRetry && (
        <div>
          <Button variant="secondary" onClick={onRetry}>
            다시 시도
          </Button>
        </div>
      )}
    </Page>
  );
}

function Rows({ items }: { items: ReactNode[] }) {
  return (
    <ul className="flex flex-col divide-y divide-line rounded-lg border border-line bg-surface">
      {items.map((item, i) => (
        <li key={i} className="px-4 py-3 text-base">
          {item}
        </li>
      ))}
    </ul>
  );
}

export function EntryScreen({ entry, onNext }: { entry: Entry; onNext: () => void }) {
  const hours = Math.round(entry.duration_minutes / 60);
  return (
    <Page>
      <div className="flex flex-col gap-2">
        <h1 className="text-2xl font-semibold">{entry.company_name} 협업 세션</h1>
        <p className="text-muted">
          가상 회사 {entry.company_name} 팀 합류 · {hours}시간 동안 기획 초안 작성
        </p>
      </div>
      <Rows
        items={[
          <>
            <b className="font-semibold">{hours}시간 연속</b> · 중간 휴식 없음 · PC 권장
          </>,
          <>
            역할: 이번 건의 <b className="font-semibold">주담당</b> · 파트 나누기, 최종본 합치기,
            마감 보고
          </>,
          "접속이 끊겨도 시간은 계속 흐름 · 같은 링크로 다시 들어오면 이어짐",
          "다른 탭의 AI·개인 메모 사용 가능 · 기록 대상은 화면 안 어시스턴트 요청만",
          <>
            문의:{" "}
            <a
              className="text-accent underline-offset-4 hover:underline"
              href={`mailto:${entry.contact_email}`}
            >
              {entry.contact_email}
            </a>
          </>,
        ]}
      />
      <div>
        <Button onClick={onNext}>다음</Button>
      </div>
    </Page>
  );
}

export const CONSENT_LINES = {
  recorded: "대화, 문서, 보드 변경, 어시스턴트 요청 원문",
  retention: "세션 종료 후 90일 보관, 이후 삭제",
  scored:
    "AI가 행동 분류 → 미리 정한 평가표 규칙이 기본 점수 계산 → 담당자가 근거를 보고 최종 조정",
  noRank: "합격·순위 판정 없음",
  assistantFree: "어시스턴트 사용 여부는 점수와 무관",
  tools: "다른 탭의 AI·개인 메모 사용 가능. 기록 대상은 이 화면 안 어시스턴트 요청만",
  assistant: '어시스턴트에게 "동료에게 뭐라고 답할까" 질문 가능(요청은 기록됨)',
  decline: "동의하지 않으면 세션 미시작 · 담당자에게 알림 없음 · 링크는 만료 전까지 유효",
};

export function ConsentScreen({
  entry,
  agreed,
  onAgreedChange,
  pending,
  error,
  onConsent,
}: {
  entry: Entry;
  agreed: boolean;
  onAgreedChange: (value: boolean) => void;
  pending?: boolean;
  error?: string | null;
  onConsent: () => void;
}) {
  return (
    <Page>
      <h1 className="text-2xl font-semibold">기록과 점수</h1>
      <ol className="flex flex-col gap-3">
        {(
          [
            ["기록", [CONSENT_LINES.recorded, CONSENT_LINES.retention]],
            ["점수 산정", [CONSENT_LINES.scored, `관찰 요소: ${entry.elements_names.join(" · ")}`]],
            ["판정하지 않는 것", [CONSENT_LINES.noRank, CONSENT_LINES.assistantFree]],
          ] as [string, string[]][]
        ).map(([title, body], i) => (
          <li key={title} className="flex gap-3 rounded-lg border border-line bg-surface px-4 py-3">
            <span className="mt-0.5 flex size-5 shrink-0 items-center justify-center rounded-full bg-accent-soft text-xs font-semibold text-accent-strong">
              {i + 1}
            </span>
            <div className="flex flex-col gap-0.5">
              <p className="text-sm font-semibold">{title}</p>
              {body.map((line) => (
                <p key={line} className="text-base">
                  {line}
                </p>
              ))}
            </div>
          </li>
        ))}
      </ol>
      <ul className="flex flex-col gap-1.5 text-sm text-muted">
        <li>{CONSENT_LINES.tools}</li>
        <li>{CONSENT_LINES.assistant}</li>
        <li>
          문의:{" "}
          <a
            className="text-accent underline-offset-4 hover:underline"
            href={`mailto:${entry.contact_email}`}
          >
            {entry.contact_email}
          </a>
        </li>
        <li>{CONSENT_LINES.decline}</li>
      </ul>
      <label className="flex items-center gap-2 text-base">
        <input
          type="checkbox"
          className="size-4 accent-[var(--color-accent)]"
          checked={agreed}
          onChange={(event) => onAgreedChange(event.target.checked)}
        />
        위 내용에 동의
      </label>
      {error && (
        <p role="alert" className="text-sm text-danger">
          {error}
        </p>
      )}
      <div>
        <Button disabled={!agreed} loading={pending} onClick={onConsent}>
          동의하고 계속
        </Button>
      </div>
    </Page>
  );
}

/** 레일 / 가운데 / 오른쪽 탭 세 영역 그림(design-direction.md ④) */
export function LayoutSketch() {
  const bar = "h-1.5 rounded-full bg-line";
  return (
    <figure className="flex flex-col gap-3">
      <div
        aria-label="오피스 화면 구성: 왼쪽 채널 목록, 가운데 대화, 오른쪽 작업 탭"
        role="img"
        className="grid h-44 grid-cols-[22%_1fr_32%] overflow-hidden rounded-lg border border-line bg-surface text-[10px]"
      >
        <div className="flex flex-col gap-1.5 bg-surface-sunken p-2.5">
          <span className="font-semibold text-ink">루프랩</span>
          <span className="rounded-sm bg-surface px-1 text-ink"># 재참여-기획</span>
          <span className="text-muted">@ 이도현</span>
          <span className="text-muted">@ 한서윤 팀장</span>
          <span className="text-muted">알림</span>
          <span className="mt-auto text-warning">마감 01:23:40</span>
        </div>
        <div className="flex flex-col gap-2 p-2.5">
          <span className="font-semibold text-ink"># 재참여-기획</span>
          <div className={`${bar} w-3/4`} />
          <div className="rounded-md border border-line p-1.5">
            <span className="rounded-sm bg-part4 px-1 text-part4-ink">4</span>{" "}
            <span className="text-ink">비슷한 서비스 사례 · v1</span>
          </div>
          <div className={`${bar} w-1/2`} />
          <div className="mt-auto h-5 rounded-md border border-line" />
        </div>
        <div className="flex flex-col gap-1.5 border-l border-line p-2.5">
          <div className="flex gap-1.5 text-muted">
            <span className="text-ink underline underline-offset-4">내 문서</span>
            <span>보드</span>
            <span>자료</span>
            <span>AI</span>
          </div>
          <div className={`${bar} w-full`} />
          <div className={`${bar} w-5/6`} />
          <div className={`${bar} w-2/3`} />
          <span className="mt-auto text-ink">★ 최종본</span>
        </div>
      </div>
      <figcaption className="grid grid-cols-3 gap-3 text-sm text-muted">
        <span>
          <b className="font-semibold text-ink">왼쪽</b> 팀 채널·동료 DM·팀장 DM·개인 알림(나만
          받음)
        </span>
        <span>
          <b className="font-semibold text-ink">가운데</b> 대화, 받은 문서 열기
        </span>
        <span>
          <b className="font-semibold text-ink">오른쪽</b> 내 문서·보드·자료·어시스턴트
        </span>
      </figcaption>
    </figure>
  );
}

/** 대기 화면과 오피스 "?"가 함께 쓰는 설명 */
export function HelpContent() {
  return (
    <div className="flex flex-col gap-5">
      <section className="flex flex-col gap-3">
        <h2 className="text-lg font-semibold">함께 일할 팀</h2>
        <div className="flex gap-3">
          <Avatar label="서" tone="manager" size={36} online name="한서윤" />
          <p className="text-base">
            <b className="font-semibold">한서윤 팀장</b>
            <span className="text-muted"> · 팀장 · 항상 온라인</span>
            <br />
            과제 맥락·조건·배경 질문 담당. 정답·판단은 주담당 몫
          </p>
        </div>
        <div className="flex gap-3">
          <Avatar label="도" tone="colleague" size={36} online name="이도현" />
          <p className="text-base">
            <b className="font-semibold">이도현</b>
            <span className="text-muted"> · 동료</span>
            <br />
            사람 팀원 역할의 AI. 동료의 요청·피드백도 업무의 일부
          </p>
        </div>
        <p className="rounded-md bg-surface-sunken px-3 py-2 text-base">{PRIMARY_ROLE_LINE}</p>
      </section>
      <section className="flex flex-col gap-3">
        <h2 className="text-lg font-semibold">진행 순서</h2>
        <ol className="flex flex-col gap-1 text-base">
          {WORK_STEPS.map((step, i) => (
            <li key={step} className="flex gap-2">
              <span className="font-semibold text-accent-strong tabular-nums">{"①②③"[i]}</span>
              {step}
            </li>
          ))}
        </ol>
      </section>
      <section className="flex flex-col gap-3">
        <h2 className="text-lg font-semibold">화면 구성</h2>
        <LayoutSketch />
        <p className="text-sm text-muted">{DOC_FLOW_LINE}</p>
      </section>
    </div>
  );
}

export function WaitingScreen({
  entry,
  pending,
  error,
  onStart,
}: {
  entry: Entry;
  pending?: boolean;
  error?: string | null;
  onStart: () => void;
}) {
  return (
    <Page width="max-w-2xl">
      <div className="flex flex-col gap-2">
        <h1 className="text-2xl font-semibold">시작 전 확인</h1>
        <p className="rounded-md border border-warning/30 bg-warning-soft px-3 py-2 text-base text-ink">
          시작 즉시 시간이 흐르고 접속이 끊겨도 멈추지 않음 ·{" "}
          {Math.round(entry.duration_minutes / 60)}
          시간과 안정적인 네트워크 필요
        </p>
      </div>
      <HelpContent />
      <p className="text-sm text-muted">이 설명은 오피스 오른쪽 위 ? 버튼으로 다시 보기</p>
      {error && (
        <p role="alert" className="text-sm text-danger">
          {error}
        </p>
      )}
      <div>
        <Button loading={pending} onClick={onStart}>
          시작하기
        </Button>
      </div>
    </Page>
  );
}
