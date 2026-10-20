// 오피스에 들어가기 전 화면: 링크 안내(만료·취소·없음), 입장, 안내·동의, 시작 대기.
// 문구의 정본은 PRD 7.3·7.4.
import { Button, Card } from "@/components/ui";

import type { Entry } from "./types";

function Shell({ children }: { children: React.ReactNode }) {
  return <main className="mx-auto flex max-w-2xl flex-col gap-4 px-6 py-16">{children}</main>;
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
    <Shell>
      <Card title={title}>
        <p className="text-muted">{description}</p>
        {onRetry && (
          <Button className="mt-4" variant="secondary" onClick={onRetry}>
            다시 시도
          </Button>
        )}
      </Card>
    </Shell>
  );
}

export function EntryScreen({ entry, onNext }: { entry: Entry; onNext: () => void }) {
  const hours = entry.duration_minutes % 60 === 0;
  return (
    <Shell>
      <p className="text-sm text-muted">{entry.company_name}</p>
      <h1 className="text-2xl font-semibold">협업 과제 안내</h1>
      <Card>
        <dl className="grid grid-cols-[6rem_1fr] gap-y-2 text-sm">
          <dt className="text-muted">소요 시간</dt>
          <dd>{hours ? `${entry.duration_minutes / 60}시간` : `${entry.duration_minutes}분`}</dd>
        </dl>
        <p className="mt-4">{entry.entry_notice}</p>
      </Card>
      <div className="flex justify-end">
        <Button onClick={onNext}>다음</Button>
      </div>
    </Shell>
  );
}

export type ConsentScreenProps = {
  entry: Entry;
  agreed: boolean;
  onAgreedChange: (agreed: boolean) => void;
  pending?: boolean;
  error?: string | null;
  onConsent: () => void;
};

export function ConsentScreen({
  entry,
  agreed,
  onAgreedChange,
  pending,
  error,
  onConsent,
}: ConsentScreenProps) {
  const observed = [...entry.elements_names, "AI 활용"];
  return (
    <Shell>
      <h1 className="text-2xl font-semibold">진행 방식과 기록 안내</h1>
      <Card>
        <ul className="flex list-disc flex-col gap-2 pl-5 text-sm">
          <li>
            가상 회사의 팀원으로 실제 업무처럼 일하는 협업 과제입니다. 함께 일하는 팀장과 동료는
            AI입니다.
          </li>
          <li>
            관찰하는 요소: {observed.join(", ")}. 세부 평가표 항목은 과제가 끝난 뒤 안내합니다.
          </li>
          <li>
            메시지, 문서 작성과 수정, 회사 문서 열람, AI 어시스턴트 요청이 기록되며 90일 동안
            보관됩니다.
          </li>
          <li>
            AI 어시스턴트를 자유롭게 쓸 수 있고 요청 내용은 기록됩니다. 사용 여부는 점수에 들어가지
            않습니다.
          </li>
          <li>
            행동은 관찰 기록으로 남고, AI가 행동을 분류한 결과를 입력으로 미리 정해진 평가표 규칙이
            기본 점수를 계산하며, 최종 점수와 판단은 채용 담당자가 근거를 확인해 직접 조정합니다.
          </li>
        </ul>
        <label className="mt-5 flex items-center gap-2 text-sm font-medium">
          <input
            type="checkbox"
            checked={agreed}
            onChange={(event) => onAgreedChange(event.target.checked)}
          />
          위 내용을 읽었고 동의합니다
        </label>
        {error && <p className="mt-2 text-sm text-danger">{error}</p>}
      </Card>
      <div className="flex justify-end">
        <Button disabled={!agreed} loading={pending} onClick={onConsent}>
          동의하고 계속
        </Button>
      </div>
    </Shell>
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
    <Shell>
      <h1 className="text-2xl font-semibold">시작하기 전에</h1>
      <Card title="함께 일할 팀">
        <p className="text-sm">
          {entry.entry_notice} 팀장 한 명과 동료 기획자 한 명이 같은 과제를 함께 진행합니다.
        </p>
      </Card>
      <Card title="화면 구성">
        <ul className="flex list-disc flex-col gap-2 pl-5 text-sm">
          <li>왼쪽: 팀 채널과 동료 DM</li>
          <li>가운데: 대화와 입력창</li>
          <li>
            오른쪽: 기획안 문서, 태스크 보드, 회사 문서, AI 어시스턴트. 기획안에서 동료가 맡은
            파트는 읽기만 할 수 있어요.
          </li>
          <li>AI 어시스턴트는 도구이고, 동료는 자기 파트만 쓰는 팀원입니다.</li>
          <li>위쪽에 남은 시간이 보이고, 시간이 다 되면 자동으로 제출됩니다.</li>
        </ul>
      </Card>
      {error && <p className="text-sm text-danger">{error}</p>}
      <div className="flex items-center justify-end gap-3">
        <p className="text-sm text-muted">시작하면 바로 시간이 흐릅니다.</p>
        <Button loading={pending} onClick={onStart}>
          시작하기
        </Button>
      </div>
    </Shell>
  );
}
