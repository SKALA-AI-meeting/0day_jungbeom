"use client";

import { Toaster as Sonner, toast } from "sonner";

/** 저장·보내기·편집 중 새 메시지 안내(Sonner). 화면에 한 번만 둔다. */
export function Toaster() {
  return (
    <Sonner
      position="bottom-center"
      toastOptions={{
        className:
          "!rounded-lg !border !border-line !bg-surface !font-sans !text-ink !shadow-[var(--shadow-float)]",
      }}
    />
  );
}

export { toast };
