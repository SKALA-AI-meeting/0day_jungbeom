"use client";

// 회사 문서: 목록과 본문. 공개 전 문서는 잠겨 있고 document.released가 오면 열린다.
import { useState } from "react";

import { Badge, cn } from "@/components/ui";

import type { OfficeState } from "./reducer";

export type OpenDoc = (docId: string) => Promise<{ title: string; content: string }>;

export function CompanyDocs({ state, onOpen }: { state: OfficeState; onOpen: OpenDoc }) {
  const [open, setOpen] = useState<{ doc_id: string; title: string; content: string } | null>(null);
  const [error, setError] = useState<string | null>(null);

  const show = async (docId: string) => {
    setError(null);
    try {
      setOpen({ doc_id: docId, ...(await onOpen(docId)) });
    } catch {
      setError("문서를 열지 못했어요. 잠시 후 다시 눌러 주세요.");
    }
  };

  return (
    <div className="flex flex-col gap-3 p-4">
      <ul className="flex flex-col gap-1">
        {state.documents.map((doc) => (
          <li key={doc.doc_id}>
            <button
              type="button"
              disabled={!doc.released}
              onClick={() => show(doc.doc_id)}
              className={cn(
                "flex w-full items-center justify-between rounded-md px-2 py-1.5 text-left text-sm",
                doc.released ? "hover:bg-surface-sunken" : "cursor-not-allowed text-subtle",
                open?.doc_id === doc.doc_id && "bg-accent-soft",
              )}
            >
              <span>{doc.title}</span>
              {!doc.released ? (
                <Badge>아직 공유되지 않음</Badge>
              ) : (
                state.fresh.includes(doc.doc_id) && <Badge tone="accent">새 문서</Badge>
              )}
            </button>
          </li>
        ))}
      </ul>
      {error && <p className="text-sm text-danger">{error}</p>}
      {open && (
        <article className="rounded-md border border-line bg-surface p-4">
          <h3 className="mb-2 font-medium">{open.title}</h3>
          <p className="text-sm whitespace-pre-wrap">{open.content}</p>
        </article>
      )}
    </div>
  );
}
