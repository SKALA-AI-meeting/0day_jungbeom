import Link from "next/link";

import { Wordmark } from "@/components/ui";
import { MOCK } from "@/lib/api";

// 루트는 안내만 한다. 지원자는 받은 초대 링크(/s/[token]), 채용 담당자는 관리자 화면(/admin).
// mock에서는 15분 데모 링크를 함께 보인다.
export default function Home() {
  return (
    <main className="mx-auto flex min-h-dvh max-w-xl flex-col justify-center gap-6 px-6 py-24">
      <Wordmark className="h-6 self-start" />
      <p className="text-callout text-muted">
        지원자는 받은 초대 링크로 접속합니다. 채용 담당자는 관리자 화면을 씁니다.
      </p>
      <div className="flex flex-wrap gap-4">
        <Link className="text-accent underline-offset-4 hover:underline" href="/admin/login">
          관리자 로그인
        </Link>
        {MOCK && (
          <Link className="text-accent underline-offset-4 hover:underline" href="/s/demo">
            15분 데모 세션
          </Link>
        )}
      </div>
    </main>
  );
}
