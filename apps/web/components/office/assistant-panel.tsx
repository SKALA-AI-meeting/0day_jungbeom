"use client";

// AI 어시스턴트: 요청·응답 목록과 인용 문서명. 요청을 보내면 응답이 올 때까지 대기 표시.
import { useState } from "react";

import { Button, EmptyState, Textarea } from "@/components/ui";

import { assistantBusy, type OfficeState } from "./reducer";

export function AssistantPanel({
  state,
  disabled,
  error,
  onAsk,
}: {
  state: OfficeState;
  disabled?: boolean;
  error?: string | null;
  onAsk: (prompt: string) => void;
}) {
  const [prompt, setPrompt] = useState("");
  const busy = assistantBusy(state);
  const titles = new Map(state.documents.map((d) => [d.doc_id, d.title]));

  return (
    <div className="flex flex-col gap-3 p-4">
      {state.assistant.length === 0 && (
        <EmptyState
          title="무엇을 도와드릴까요?"
          description="공유된 회사 문서를 찾아 요약하거나 초안을 잡아 드려요."
        />
      )}
      <ol className="flex flex-col gap-3">
        {state.assistant.map((call) => (
          <li key={call.call_id} className="flex flex-col gap-1.5">
            <p className="self-end rounded-md bg-accent-soft px-3 py-2 text-sm whitespace-pre-wrap">
              {call.request}
            </p>
            {call.pending ? (
              <p className="text-sm text-muted" aria-live="polite">
                답변 작성 중…
              </p>
            ) : (
              <div className="rounded-md border border-line bg-surface px-3 py-2 text-sm">
                <p className="whitespace-pre-wrap">{call.response ?? "답변을 받지 못했어요."}</p>
                {call.cited_docs.length > 0 && (
                  <p className="mt-2 text-xs text-muted">
                    참고한 문서: {call.cited_docs.map((id) => titles.get(id) ?? id).join(", ")}
                  </p>
                )}
              </div>
            )}
          </li>
        ))}
      </ol>
      {error && <p className="text-sm text-danger">{error}</p>}
      <form
        className="flex flex-col gap-2"
        onSubmit={(event) => {
          event.preventDefault();
          const text = prompt.trim();
          if (!text || busy || disabled) return;
          onAsk(text);
          setPrompt("");
        }}
      >
        <Textarea
          aria-label="어시스턴트에게 요청"
          value={prompt}
          disabled={disabled}
          placeholder="예: 지표 현황에서 재참여율을 찾아 줘"
          onChange={(event) => setPrompt(event.target.value)}
        />
        <div className="flex justify-end">
          <Button type="submit" size="sm" loading={busy} disabled={disabled || !prompt.trim()}>
            요청
          </Button>
        </div>
      </form>
    </div>
  );
}
