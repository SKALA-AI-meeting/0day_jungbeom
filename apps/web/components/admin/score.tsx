import { Badge } from "@/components/ui";

import { tallyText } from "./format";
import type { CandidateScore } from "./types";

/** 요소별 칩 `협력 태도 2/3`. 기록 없음은 회색으로 따로 표시한다. */
export function ScoreChips({
  score,
  names,
}: {
  score: CandidateScore;
  names: Map<string, string>;
}) {
  return (
    <div className="flex flex-wrap gap-1.5">
      {score.by_element.map((row) => (
        <span key={row.element} className="inline-flex items-center gap-1">
          <Badge tone={row.judged === 0 ? "neutral" : "accent"}>
            {names.get(row.element) ?? row.element}{" "}
            {row.judged === 0 ? "–/0" : `${row.met}/${row.judged}`}
          </Badge>
          {row.judged < 4 && <Badge tone="neutral">기록 없음 {4 - row.judged}</Badge>}
        </span>
      ))}
    </div>
  );
}

/** 합계와 출처(기본 점수 = 자동, 담당자 점수 = 검토자 조정). 순위·판정 표현은 쓰지 않는다. */
export function ScoreTotal({ score }: { score: CandidateScore }) {
  return (
    <span className="inline-flex items-center gap-2">
      <span className="font-medium">{tallyText(score)}</span>
      <Badge tone={score.source === "reviewer" ? "success" : "neutral"}>
        {score.source === "reviewer" ? "담당자 점수" : "기본 점수"}
      </Badge>
    </span>
  );
}
