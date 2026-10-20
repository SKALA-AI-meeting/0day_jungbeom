import Link from "next/link";

// 루트는 안내만 한다. 관리자 화면(/admin)은 web-admin, 지원자 화면(/s/[token])은 web-office 트랙.
export default function Home() {
  return (
    <main className="mx-auto flex max-w-xl flex-col gap-4 px-6 py-24">
      <h1 className="text-2xl font-semibold">Day Zero</h1>
      <p className="text-muted">
        초대 링크로 들어온 지원자는 받은 주소로 접속합니다. 채용 담당자는 관리자 화면을 쓰세요.
      </p>
      <Link className="text-accent underline-offset-4 hover:underline" href="/admin/login">
        관리자 로그인
      </Link>
    </main>
  );
}
