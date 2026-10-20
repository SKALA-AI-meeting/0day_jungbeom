"use client";

// 오른쪽 "어시스턴트" 탭: 요청·응답 목록과 인용 문서. 어시스턴트는 내 문서에 직접 쓰지 않으므로 복사가 기본 동선이다.
import { useState, type FormEvent } from "react";

import { Button, Chip, toast } from "@/components/ui";

import { clock } from "./lines";
import type { AssistantCall, CompanyDoc } from "./types";

export async function copyText(text: string) {
  try {
    await navigator.clipboard.writeText(text);
    toast("복사했어요");
  } catch {
    // 권한이 없으면(비보안 컨텍스트 등) 사용자가 직접 고를 수 있게 안내만 한다
    toast("복사하지 못했어요. 텍스트를 직접 선택해 주세요.");
  }
}

export function AssistantPanel({
  calls,
  documents,
  locked,
  pending,
  error,
  onAsk,
}: {
  calls: AssistantCall[];
  documents: CompanyDoc[];
  locked: boolean;
  pending: string | null;
  error: string | null;
  onAsk: (prompt: string) => void;
}) {
  const [text, setText] = useState("");
  const title = (id: string) => documents.find((d) => d.doc_id === id)?.title ?? id;
  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (!text.trim() || pending) return;
    onAsk(text.trim());
    setText("");
  };
  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="min-h-0 flex-1 overflow-y-auto p-5">
        {calls.length === 0 && !pending && (
          <p className="text-sm text-muted">
            회사 자료 검색·요약·문장 다듬기 · 요청과 응답은 기록됨
          </p>
        )}
        <ol className="flex flex-col gap-4">
          {calls.map((call) => (
            <li key={call.call_id} className="flex flex-col gap-2">
              <p className="self-end rounded-md bg-accent-soft px-3 py-2 text-sm whitespace-pre-wrap">
                {call.request}
              </p>
              <div className="rounded-md border border-line bg-surface px-3 py-2.5">
                <p className="text-sm leading-6 whitespace-pre-wrap">{call.response}</p>
                <div className="mt-2 flex flex-wrap items-center gap-1.5">
                  {call.cited_docs.map((id) => (
                    <Chip key={id} tone="outline">
                      {title(id)}
                    </Chip>
                  ))}
                  <span className="text-xs text-subtle tabular-nums">{clock(call.t_min)}</span>
                  <Button
                    size="xs"
                    variant="ghost"
                    className="ml-auto"
                    onClick={() => void copyText(call.response)}
                  >
                    복사
                  </Button>
                </div>
              </div>
            </li>
          ))}
          {pending && (
            <li className="flex flex-col gap-2">
              <p className="self-end rounded-md bg-accent-soft px-3 py-2 text-sm whitespace-pre-wrap">
                {pending}
              </p>
              <p className="text-sm text-muted">응답을 기다리는 중…</p>
            </li>
          )}
        </ol>
        {error && (
          <p role="alert" className="mt-3 text-sm text-danger">
            {error}
          </p>
        )}
      </div>
      <form onSubmit={submit} className="flex shrink-0 items-end gap-2 border-t border-line p-3">
        <textarea
          value={text}
          rows={2}
          disabled={locked}
          onChange={(event) => setText(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing)
              submit(event);
          }}
          placeholder={locked ? "제출 뒤에는 쓸 수 없어요" : "어시스턴트에게 물어보기"}
          aria-label="어시스턴트 요청"
          className="min-h-9 flex-1 resize-none rounded-md border border-line px-2.5 py-1.5 text-sm outline-none focus:border-accent/60"
        />
        <Button size="sm" type="submit" disabled={locked || !text.trim() || !!pending}>
          묻기
        </Button>
      </form>
    </div>
  );
}
