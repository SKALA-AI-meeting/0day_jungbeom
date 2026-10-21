"use client";

// 기획안(ProposalEditor): 우측 탭 안 6칸 세로 폼(UX 결정 6). 예시 문장 없이 칸이 무엇인지만 한 줄로 쓴다.
// idea_credit 안내는 R7 고정 문구. 제출은 기획안 작성 단계에서만, 확인 창 하나를 거친다.
import { useState } from "react";

import { Button, ConfirmDialog } from "@/components/ui";

import { SECTION_IDS, type SectionId, type Sections } from "./types";

export const SECTION_META: Record<SectionId, { title: string; hint: string }> = {
  keyword: { title: "키워드", hint: "정한 키워드" },
  problem: { title: "문제 상황", hint: "정한 문제 상황" },
  solution: { title: "해결책", hint: "정한 해결 방향" },
  rationale: { title: "근거", hint: "이 기획을 뒷받침하는 근거" },
  expected_effect: { title: "기대효과", hint: "이 기획으로 기대하는 효과" },
  idea_credit: { title: "아이디어 기여", hint: "이 기획에 반영된 의견과 그 의견을 낸 사람" },
};

export function ProposalEditor({
  sections,
  savedAt,
  saving,
  canSubmit,
  locked,
  onChange,
  onSubmit,
}: {
  sections: Sections;
  /** 마지막 저장 시각(표시용 "HH:MM:SS") */
  savedAt: string | null;
  saving: boolean;
  canSubmit: boolean;
  locked: boolean;
  onChange: (id: SectionId, value: string) => void;
  onSubmit: () => Promise<void>;
}) {
  const [open, setOpen] = useState(false);
  const [pending, setPending] = useState(false);
  return (
    <div className="flex flex-col">
      <div className="flex flex-col gap-6 px-6 py-5">
        {SECTION_IDS.map((id) => (
          <label key={id} className="flex flex-col gap-1">
            <span className="text-title3 font-semibold">{SECTION_META[id].title}</span>
            <span className="text-footnote text-muted">{SECTION_META[id].hint}</span>
            <textarea
              value={sections[id]}
              disabled={locked}
              rows={id === "keyword" ? 1 : 2}
              data-section={id}
              onChange={(event) => onChange(id, event.target.value)}
              className="mt-1 resize-none border-0 border-b border-line bg-transparent px-0 py-2 text-body outline-none field-sizing-content focus-visible:border-accent disabled:text-muted"
            />
          </label>
        ))}
      </div>
      <div className="sticky bottom-0 flex bg-surface items-center gap-3 border-t border-line px-6 py-3">
        <span className="text-footnote text-muted tabular-nums" aria-live="polite">
          {locked
            ? "제출했어요"
            : saving
              ? "저장 중…"
              : savedAt
                ? `${savedAt} 저장됨`
                : "자동 저장"}
        </span>
        {!canSubmit && !locked && (
          <span className="text-footnote text-muted">기획안 작성 단계에서 제출할 수 있어요</span>
        )}
        <Button
          className="ml-auto"
          size="sm"
          disabled={!canSubmit || locked}
          onClick={() => setOpen(true)}
        >
          제출
        </Button>
      </div>
      <ConfirmDialog
        open={open}
        onOpenChange={setOpen}
        title="제출하면 수정할 수 없어요"
        confirmLabel="제출"
        pending={pending}
        onConfirm={async () => {
          setPending(true);
          await onSubmit();
          setPending(false);
          setOpen(false);
        }}
      />
    </div>
  );
}
