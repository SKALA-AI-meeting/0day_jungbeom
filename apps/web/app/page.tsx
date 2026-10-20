import Link from "next/link";

// 루트는 안내만 한다. 관리자 화면은 /admin, 지원자 화면은 초대 링크(/s/[token]).
export default function Home() {
  return (
    <main className="mx-auto flex max-w-xl flex-col gap-4 px-6 py-24">
      <h1 className="text-2xl font-semibold">Day Zero</h1>
      <p className="text-muted">지원자: 받은 초대 링크로 접속 · 채용 담당자: 관리자 화면</p>
      <Link className="text-accent underline-offset-4 hover:underline" href="/admin/login">
        관리자 로그인
      </Link>
    </main>
  );
}
