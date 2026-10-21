// 리포트 생성 실패 화면. [다시 만들기]는 재생성을 요청하고, 성공하면 부모가 "만드는 중" 폴링으로 돌아간다.
import { CircleAlert } from "lucide-react";

import { Button } from "@/components/ui";

export function ReportFailed({
  failedStep,
  pending,
  error,
  onRegenerate,
}: {
  /** 실패 지점: finalize면 확정 단계 문구를 덧붙인다 */
  failedStep?: string | null;
  pending?: boolean;
  /** 재생성 요청 오류 문구 */
  error?: string | null;
  onRegenerate: () => void;
}) {
  return (
    <div
      role="alert"
      className="mx-auto flex w-full max-w-3xl flex-col gap-3 rounded-lg bg-danger-soft px-4 py-3"
    >
      <p className="flex items-center gap-2 text-body text-ink">
        <CircleAlert size={16} className="shrink-0 text-danger" aria-hidden />
        리포트를 만들지 못했어요.{failedStep === "finalize" && " 확정 단계에서 멈췄어요."}
      </p>
      {error && <p className="text-sm text-danger">{error}</p>}
      <div>
        <Button size="sm" variant="secondary" loading={pending} onClick={onRegenerate}>
          다시 만들기
        </Button>
      </div>
    </div>
  );
}
