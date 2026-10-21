import { Badge, type BadgeTone } from "./badge";

/** docs/contracts/api.md의 display_status: 세션 status에 만료(expired)를 더한 표시값. */
export type DisplayStatus =
  | "invited"
  | "expired"
  | "cancelled"
  | "in_progress"
  | "reporting"
  | "completed"
  | "report_ready"
  | "approving"
  | "reviewed"
  | "failed";

export const STATUS_LABELS: Record<DisplayStatus, string> = {
  invited: "초대됨",
  expired: "만료",
  cancelled: "취소",
  in_progress: "진행 중",
  reporting: "보고 중",
  completed: "완료",
  report_ready: "리포트 준비됨",
  approving: "확정 중",
  reviewed: "검토 완료",
  failed: "실패",
};

const TONES: Record<DisplayStatus, BadgeTone> = {
  invited: "neutral",
  expired: "neutral",
  cancelled: "neutral",
  in_progress: "accent",
  reporting: "accent",
  completed: "accent",
  report_ready: "warning",
  approving: "warning",
  reviewed: "success",
  failed: "danger",
};

export type StatusBadgeProps = { status: DisplayStatus; className?: string };

export function StatusBadge({ status, className }: StatusBadgeProps) {
  return (
    <Badge tone={TONES[status]} className={className}>
      {STATUS_LABELS[status]}
    </Badge>
  );
}
