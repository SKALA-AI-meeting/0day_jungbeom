"use client";

// break-ui 점검용 Demo / Worst case 전환(NEXT_PUBLIC_MOCK=1에서만). 주소의 ?data=worst로 남겨 새로고침해도 유지된다.
// mock 서버 상태가 모듈 안에 있으므로 전체 새로고침으로 바꾼다.
// 화면 오른쪽 아래 접힘 칩으로 두어 아무것도 덮지 않는다. 오피스(/s/)는 "mock 조작" 패널 안에 같은 전환이 있다.
import { usePathname } from "next/navigation";
import { useState, useSyncExternalStore } from "react";

const read = () => new URLSearchParams(window.location.search).get("data") === "worst";

export function setWorst(next: boolean) {
  const url = new URL(window.location.href);
  if (next) url.searchParams.set("data", "worst");
  else url.searchParams.delete("data");
  window.location.assign(url.toString());
}

export function useWorst() {
  return useSyncExternalStore(
    () => () => {},
    read,
    () => false,
  );
}

export function DataToggle() {
  const worst = useWorst();
  const path = usePathname();
  const [open, setOpen] = useState(false);
  if (path.startsWith("/s/")) return null;
  return (
    <div className="no-print fixed right-2 bottom-2 z-[60] flex items-center gap-0.5 rounded-full bg-[#e5e7eb]/90 p-0.5 font-sans text-[11px] text-[#374151]">
      <button type="button" onClick={() => setOpen((v) => !v)} className="rounded-full px-2 py-0.5">
        {worst ? "worst" : "data"} {open ? "▸" : "◂"}
      </button>
      {open &&
        (
          [
            ["Demo", false],
            ["Worst case", true],
          ] as const
        ).map(([label, value]) => (
          <button
            key={label}
            type="button"
            onClick={() => setWorst(value)}
            className={`rounded-full px-2 py-0.5 ${worst === value ? "bg-white" : ""}`}
          >
            {label}
          </button>
        ))}
    </div>
  );
}
