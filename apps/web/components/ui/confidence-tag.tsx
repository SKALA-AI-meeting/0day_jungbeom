import { CircleAlert, CircleCheck, CircleDot } from "lucide-react";

import { cn } from "./cn";

/** docs/contracts/api.md dimensions[].confidence. 기록 없음 차원은 null이라 태그를 그리지 않는다 */
export type Confidence = "high" | "medium" | "low";

const LABEL: Record<Confidence, string> = { high: "높음", medium: "보통", low: "낮음" };

export type ConfidenceTagProps = { confidence: Confidence; className?: string };

/** 차원 확신도. 색만으로 구분하지 않도록 아이콘 + 글자, 낮음은 원문 확인 권장 문구를 붙인다 */
export function ConfidenceTag({ confidence, className }: ConfidenceTagProps) {
  const Icon =
    confidence === "high" ? CircleCheck : confidence === "medium" ? CircleDot : CircleAlert;
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 text-xs whitespace-nowrap",
        confidence === "low" ? "text-warning" : "text-muted",
        className,
      )}
    >
      <Icon aria-hidden className="size-3.5 shrink-0" strokeWidth={2} />
      확신도 {LABEL[confidence]}
      {confidence === "low" && <span>· 근거 약함, 원문 확인 권장</span>}
    </span>
  );
}
