"use client";

// 메인 "자료" 탭: 회사 문서 목록과 읽기 전용 Markdown 뷰어. 미공개 문서는 잠금과 "공유 예정"만 보인다.
// 시각은 쓰지 않는다: 예정 시각은 킥오프·개인 알림이 말하고, 미리 보이면 지연 장면이 새 정보가 아니게 된다.
import { useState } from "react";

import { Button, Chip } from "@/components/ui";

import { Markdown } from "./markdown";
import type { CompanyDoc } from "./types";

export function Library({
  documents,
  releasedLater,
  onRead,
  onToDocs,
}: {
  documents: CompanyDoc[];
  /** 이 창이 열려 있는 동안 공개된 문서(document.released 프레임·재동기화 스냅샷) */
  releasedLater: string[];
  /** 열람은 서버가 doc_views에 기록한다 */
  onRead: (docId: string) => Promise<string>;
  /** 읽던 자료를 그대로 두고 내 문서 탭으로(CX-06). 탭은 모두 마운트돼 있어 돌아오면 같은 자리다 */
  onToDocs?: () => void;
}) {
  const [open, setOpen] = useState<{
    doc: CompanyDoc;
    content: string | null;
    error?: string;
  } | null>(null);

  if (open) {
    return (
      <div className="flex min-h-full flex-col">
        <div className="sticky top-0 z-[1] flex items-center gap-3 border-b border-line bg-surface px-5 py-2.5">
          <button
            type="button"
            onClick={() => setOpen(null)}
            className="shrink-0 text-sm text-muted hover:text-ink"
          >
            ← 자료 목록
          </button>
          <h3 className="min-w-0 flex-1 truncate font-semibold">{open.doc.title}</h3>
          {onToDocs && (
            <Button size="xs" variant="secondary" onClick={onToDocs}>
              내 문서로
            </Button>
          )}
        </div>
        <div className="px-5 py-6">
          {open.error ? (
            <p role="alert" className="text-danger">
              {open.error}
            </p>
          ) : open.content == null ? (
            <p className="text-muted">여는 중…</p>
          ) : (
            // 읽기 폭은 한 줄 70자 안팎으로 묶는다(넓은 메인 영역에서 줄이 길어지지 않게)
            <article className="mx-auto max-w-[44rem] rounded-lg border border-line bg-surface px-6 py-6 text-base leading-7 sm:px-8">
              <Markdown>{open.content}</Markdown>
            </article>
          )}
        </div>
      </div>
    );
  }

  const read = async (doc: CompanyDoc) => {
    setOpen({ doc, content: null });
    try {
      setOpen({ doc, content: await onRead(doc.doc_id) });
    } catch {
      setOpen({ doc, content: null, error: "아직 공유되지 않은 자료" });
    }
  };

  return (
    <ul className="mx-auto flex w-full max-w-[44rem] flex-col gap-1 p-5">
      {documents.map((doc) => (
        <li key={doc.doc_id}>
          {doc.released ? (
            <button
              type="button"
              onClick={() => void read(doc)}
              className="press flex w-full items-center gap-2 rounded-md px-2.5 py-2 text-left hover:bg-surface-sunken"
            >
              <span aria-hidden className="text-muted">
                ▤
              </span>
              <span className="min-w-0 flex-1 truncate">{doc.title}</span>
              {releasedLater.includes(doc.doc_id) && <Chip tone="success">공개됨</Chip>}
            </button>
          ) : (
            <div
              className="flex items-center gap-2 rounded-md px-2.5 py-2 text-muted"
              aria-disabled
            >
              <svg viewBox="0 0 16 16" className="size-3.5 shrink-0" aria-label="잠김">
                <rect
                  x="3"
                  y="7"
                  width="10"
                  height="7"
                  rx="1.5"
                  fill="none"
                  stroke="currentColor"
                />
                <path d="M5.5 7V5a2.5 2.5 0 0 1 5 0v2" fill="none" stroke="currentColor" />
              </svg>
              <span className="min-w-0 flex-1 truncate">{doc.title}</span>
              <Chip tone="outline">공유 예정</Chip>
            </div>
          )}
        </li>
      ))}
    </ul>
  );
}
