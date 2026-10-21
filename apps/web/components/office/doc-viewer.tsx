"use client";

// 가운데 "열린 문서" 상태: 받은 동료 문서를 대화 위로 열어 읽고, 답글을 쓰거나 최종본에 가져온다.
import { AnimatePresence, motion, useReducedMotion } from "motion/react";

import { Button, Chip, DropMenu, partTone } from "@/components/ui";

import { Markdown } from "./markdown";
import type { FinalSection, ReceivedDocument } from "./types";

export type OpenDoc = {
  doc: ReceivedDocument;
  version: number;
  content: string | null;
  error?: string | null;
};

const EASE_OUT = [0.23, 1, 0.32, 1] as const;

export function DocViewer({
  open,
  owner,
  sections,
  locked,
  onVersion,
  onReply,
  onImport,
  onClose,
}: {
  open: OpenDoc | null;
  owner: string;
  sections: FinalSection[];
  locked: boolean;
  onVersion: (version: number) => void;
  onReply: () => void;
  onImport: (partNo: number) => void;
  onClose: () => void;
}) {
  const reduce = useReducedMotion();
  return (
    <AnimatePresence>
      {open && (
        <motion.section
          key={open.doc.doc_id}
          aria-label={`${open.doc.title} 문서`}
          initial={{ opacity: 0, transform: reduce ? "none" : "translateY(12px)" }}
          animate={{
            opacity: 1,
            transform: "translateY(0px)",
            transition: { duration: 0.16, ease: EASE_OUT },
          }}
          exit={{
            opacity: 0,
            transform: reduce ? "none" : "translateY(8px)",
            transition: { duration: 0.12, ease: EASE_OUT },
          }}
          className="absolute inset-0 z-10 flex flex-col bg-canvas"
        >
          <header className="flex shrink-0 flex-wrap items-center gap-2 border-b border-line bg-surface px-5 py-3 shadow-[var(--shadow-float)]">
            <Chip tone={partTone(open.doc.part_no)}>{open.doc.part_no}</Chip>
            <h2 className="min-w-0 truncate text-lg font-semibold">{open.doc.title}</h2>
            <span className="shrink-0 text-sm text-muted">{owner}</span>
            {open.doc.versions.length > 1 ? (
              <DropMenu
                trigger={
                  <button type="button" className="press shrink-0 rounded-sm">
                    <Chip tone="outline">v{open.version} ▾</Chip>
                  </button>
                }
                items={[...open.doc.versions].reverse().map((v, i) => ({
                  label: `v${v.version}${i === 0 ? " (최신)" : ""}`,
                  hint: v.opened ? "열어 봄" : undefined,
                  onSelect: () => onVersion(v.version),
                }))}
              />
            ) : (
              <Chip tone="outline">v{open.version}</Chip>
            )}
            <div className="ml-auto flex shrink-0 items-center gap-2">
              <Button size="sm" variant="secondary" onClick={onReply}>
                답글 쓰기
              </Button>
              <DropMenu
                align="end"
                trigger={
                  <Button size="sm" variant="secondary" disabled={locked || open.content == null}>
                    최종본에 가져오기
                  </Button>
                }
                items={[
                  { group: "넣을 섹션" },
                  ...sections.map((s) => ({
                    label: `${s.part_no}. ${s.title}`,
                    hint:
                      s.part_no === open.doc.part_no
                        ? "같은 파트"
                        : s.content
                          ? "내용 있음"
                          : undefined,
                    onSelect: () => onImport(s.part_no),
                  })),
                ]}
              />
              <button
                type="button"
                onClick={onClose}
                aria-label="문서 닫기"
                className="press flex size-8 items-center justify-center rounded-md text-muted hover:bg-surface-sunken"
              >
                ✕
              </button>
            </div>
          </header>
          <div className="min-h-0 flex-1 overflow-y-auto px-4 py-6 sm:px-8">
            {open.error ? (
              <p role="alert" className="text-danger">
                {open.error}
              </p>
            ) : open.content == null ? (
              <p className="text-muted">여는 중…</p>
            ) : open.content ? (
              <article className="mx-auto max-w-[44rem] rounded-lg border border-line bg-surface px-6 py-7 text-base leading-7 sm:px-8">
                <Markdown breaks>{open.content}</Markdown>
              </article>
            ) : (
              <p className="text-muted">빈 문서</p>
            )}
          </div>
        </motion.section>
      )}
    </AnimatePresence>
  );
}
