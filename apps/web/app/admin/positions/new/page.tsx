"use client";

// 채용 건 생성. 만든 뒤에는 응답의 자리 이름과 키워드 후보만 확인용으로 보이고 지원자 목록으로 넘어간다.
import Link from "next/link";
import { useState } from "react";

import { adminApi, errorMessage, useLoad, useToken } from "@/components/admin/client";
import { PositionForm } from "@/components/admin/position-form";
import type { PositionCreated, SessionMinutes } from "@/components/admin/types";
import { Avatar, Button } from "@/components/ui";

export default function NewPositionPage() {
  const token = useToken();
  const { data: catalog, error: loadError } = useLoad(adminApi.catalog);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [created, setCreated] = useState<PositionCreated | null>(null);

  async function create(value: { name: string; session_minutes: SessionMinutes }) {
    if (!token) return;
    setPending(true);
    setError(null);
    try {
      setCreated(await adminApi.createPosition(token, value));
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setPending(false);
    }
  }

  if (created) {
    return (
      <div className="mx-auto flex w-full max-w-2xl flex-col gap-6">
        <h1 className="text-title1 font-bold break-all">{created.name}</h1>
        <p className="text-muted">
          채용 건을 만들었습니다 · 세션 {created.session_minutes}분. 같은 채용 건의 지원자는 모두
          같은 장면을 겪습니다.
        </p>
        <dl className="divide-y divide-line border-y border-line">
          <div className="flex flex-col gap-2 py-3">
            <dt className="text-sm text-muted">AI 동료</dt>
            <dd className="flex flex-wrap gap-4">
              {created.seats.map((s) => (
                <span key={s.seat} className="inline-flex items-center gap-1.5">
                  <Avatar seat={s.seat} src={s.avatar_url} name={s.name} size={28} />
                  {s.name}
                </span>
              ))}
            </dd>
          </div>
          <div className="flex flex-col gap-2 py-3">
            <dt className="text-sm text-muted">키워드 후보</dt>
            <dd>{created.keywords.join(" · ")}</dd>
          </div>
        </dl>
        <div>
          <Link href={`/admin/positions/${created.id}`}>
            <Button>지원자 초대하러 가기</Button>
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="mx-auto flex w-full max-w-2xl flex-col gap-8">
      <div>
        <Link href="/admin/positions" className="text-sm text-muted hover:underline">
          ← 채용 건 목록
        </Link>
        <h1 className="mt-1 text-title1 font-bold">채용 건 만들기</h1>
      </div>
      {loadError && (
        <p role="alert" className="text-danger">
          {loadError}
        </p>
      )}
      {catalog && (
        <PositionForm catalog={catalog} pending={pending} error={error} onSubmit={create} />
      )}
    </div>
  );
}
