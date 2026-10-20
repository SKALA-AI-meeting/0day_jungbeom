"use client";

// 기획안 문서: 파트 5개. 내 파트는 입력 1초 뒤 저장되고, 동료 파트는 읽기 전용이다.
import { useState } from "react";

import { Badge, Textarea } from "@/components/ui";

import { PART_NUMBERS, PART_TITLES, callName } from "./parts";
import type { OfficeState } from "./reducer";
import type { Assignee } from "./types";

const ASSIGNEE_LABEL: Record<Assignee, string> = {
  candidate: "내 담당",
  colleague: "동료 담당",
  both: "함께",
};

export function PlanDoc({
  state,
  disabled,
  onEdit,
  onRetry,
}: {
  state: OfficeState;
  disabled?: boolean;
  onEdit: (partNo: number, content: string) => void;
  onRetry: (partNo: number) => void;
}) {
  const [hinted, setHinted] = useState<number | null>(null);
  const colleague = callName(state.persona.colleague);
  return (
    <div className="flex flex-col gap-5 p-4">
      {PART_NUMBERS.map((partNo) => {
        const part = state.document[partNo] ?? { content: "", revision: 0, dirty: false };
        const assignee = state.tasks.find((t) => t.part_no === partNo)?.assignee;
        const readOnly = assignee === "colleague";
        return (
          <div key={partNo} className="flex flex-col gap-1.5">
            <div className="flex items-center gap-2">
              <span className="text-sm font-medium">
                {partNo}. {PART_TITLES[partNo]}
              </span>
              {assignee && (
                <Badge tone={assignee === "colleague" ? "neutral" : "accent"}>
                  {ASSIGNEE_LABEL[assignee]}
                </Badge>
              )}
              {part.failed ? (
                <span className="flex items-center gap-1.5 text-xs text-danger">
                  저장 실패
                  <button
                    type="button"
                    className="underline underline-offset-2"
                    onClick={() => onRetry(partNo)}
                  >
                    다시 시도
                  </button>
                </span>
              ) : (
                !readOnly && part.dirty && <span className="text-xs text-subtle">저장 중…</span>
              )}
            </div>
            <Textarea
              aria-label={`${partNo}. ${PART_TITLES[partNo]}`}
              value={part.content}
              readOnly={readOnly}
              disabled={disabled && !readOnly}
              placeholder={readOnly ? "아직 작성 전이에요" : "내용을 입력하세요"}
              hint={
                state.rejected.includes(partNo)
                  ? `${colleague} 담당 파트라 입력한 내용이 저장되지 않았어요. 필요한 내용은 DM으로 전해 주세요`
                  : readOnly && hinted === partNo
                    ? `${colleague} 담당 파트예요. 수정 요청은 DM으로`
                    : undefined
              }
              onClick={() => readOnly && setHinted(partNo)}
              onFocus={() => readOnly && setHinted(partNo)}
              onChange={(event) => !readOnly && onEdit(partNo, event.target.value)}
              className="min-h-28"
            />
          </div>
        );
      })}
    </div>
  );
}
