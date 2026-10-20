"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useSyncExternalStore, type ReactNode } from "react";

import { Button } from "@/components/ui";

import { setToken, useToken } from "./client";

const OPEN_PATHS = ["/admin/login", "/admin/signup"];

/** /admin 공통 틀. 토큰이 없으면 로그인 화면으로 보내고, 그 전에는 본문을 그리지 않는다. */
export function AdminShell({ children }: { children: ReactNode }) {
  const token = useToken();
  const path = usePathname();
  const router = useRouter();
  const open = OPEN_PATHS.includes(path);
  // 하이드레이션 전에는 token이 서버 스냅샷(null)이므로, 브라우저에서 값을 읽은 뒤에만 로그인 여부를 따진다
  const hydrated = useSyncExternalStore(
    () => () => {},
    () => true,
    () => false,
  );

  useEffect(() => {
    if (hydrated && !token && !open) router.replace("/admin/login");
  }, [hydrated, token, open, router]);

  if (open) return <>{children}</>;
  if (!token) return null;

  return (
    <div className="min-h-dvh">
      <header className="border-b border-line bg-surface">
        <div className="mx-auto flex max-w-5xl items-center justify-between px-6 py-3">
          <Link href="/admin/positions" className="font-semibold">
            Day Zero 관리자
          </Link>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => {
              setToken(null);
              router.replace("/admin/login");
            }}
          >
            로그아웃
          </Button>
        </div>
      </header>
      <main className="mx-auto flex max-w-5xl flex-col gap-6 px-6 py-8">{children}</main>
    </div>
  );
}
