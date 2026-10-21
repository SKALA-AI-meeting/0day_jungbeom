"use client";

import { Dialog } from "@base-ui/react/dialog";
import type { ReactNode } from "react";

import { Button } from "./button";

export type ConfirmDialogProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: ReactNode;
  description?: ReactNode;
  confirmLabel?: string;
  cancelLabel?: string;
  /** 확인 버튼 색. 되돌릴 수 없는 동작(제출 등)은 danger */
  tone?: "primary" | "danger";
  /** 확인 처리 중이면 true(버튼 비활성) */
  pending?: boolean;
  /** 설명 아래 추가 내용(입력란 등) */
  children?: ReactNode;
  onConfirm: () => void;
};

export function ConfirmDialog({
  open,
  onOpenChange,
  title,
  description,
  confirmLabel = "확인",
  cancelLabel = "취소",
  tone = "primary",
  pending,
  onConfirm,
  children,
}: ConfirmDialogProps) {
  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Backdrop className="fixed inset-0 z-40 bg-black/25 transition-opacity duration-[180ms] data-[ending-style]:opacity-0 data-[starting-style]:opacity-0" />
        <Dialog.Popup className="fixed top-1/2 left-1/2 z-50 w-[min(28rem,calc(100vw-2rem))] -translate-x-1/2 -translate-y-1/2 rounded-xl bg-surface p-6 shadow-[var(--shadow-float)] transition-[scale,opacity] duration-[180ms] ease-[var(--ease-out)] data-[ending-style]:scale-[0.98] data-[ending-style]:opacity-0 data-[ending-style]:duration-[120ms] data-[starting-style]:scale-[0.98] motion-reduce:data-[ending-style]:scale-100 motion-reduce:data-[starting-style]:scale-100 data-[starting-style]:opacity-0">
          <Dialog.Title className="text-title3 font-semibold">{title}</Dialog.Title>
          {description && (
            <Dialog.Description className="mt-2 text-muted">{description}</Dialog.Description>
          )}
          {children}
          <div className="mt-6 flex justify-end gap-2">
            <Dialog.Close render={<Button variant="secondary" />}>{cancelLabel}</Dialog.Close>
            <Button variant={tone} loading={pending} onClick={onConfirm}>
              {confirmLabel}
            </Button>
          </div>
        </Dialog.Popup>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
