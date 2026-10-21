"use client";

// 채용 건 상세: 지원자 목록(상태 묶음·요소별 수준 칩)과 초대 폼, 행 액션(링크 재발급·재응시 초대·리포트 다시 생성·취소).
import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";

import { CandidateTable, InviteForm, InviteResultBox } from "@/components/admin/candidates";
import { adminApi, errorMessage, useLoad, useToken } from "@/components/admin/client";
import type { Candidate, InviteResult } from "@/components/admin/types";
import { Toaster } from "@/components/ui";

export default function PositionDetailPage() {
  const { id } = useParams<{ id: string }>();
  const token = useToken();
  const { data, error, reload } = useLoad(async (t) => {
    const [positions, candidates] = await Promise.all([
      adminApi.positions(t),
      adminApi.candidates(t, id),
    ]);
    return { position: positions.find((p) => p.id === id), candidates };
  }, id);
  const [pending, setPending] = useState(false);
  const [inviteError, setInviteError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [result, setResult] = useState<{ title: string; value: InviteResult } | null>(null);
  const [formKey, setFormKey] = useState(0);

  async function run(title: string, action: () => Promise<InviteResult | unknown>) {
    setActionError(null);
    try {
      const value = await action();
      if (value && typeof value === "object" && "invite_url" in value) {
        setResult({ title, value: value as InviteResult });
      }
    } catch (e) {
      setActionError(errorMessage(e));
    }
    reload();
  }

  async function invite(value: { alias: string; email: string }) {
    if (!token) return;
    setPending(true);
    setInviteError(null);
    try {
      setResult({
        title: `${value.alias} 초대 링크`,
        value: await adminApi.invite(token, id, value),
      });
      setFormKey((k) => k + 1);
      reload();
    } catch (e) {
      setInviteError(errorMessage(e));
    } finally {
      setPending(false);
    }
  }

  const position = data?.position;
  return (
    <>
      <div>
        <Link href="/admin/positions" className="text-sm text-muted hover:underline">
          ← 채용 건 목록
        </Link>
        <h1 className="mt-1 text-title1 font-bold break-all">{position?.name ?? "채용 건"}</h1>
        {position && (
          <p className="text-sm text-muted">
            세션 {position.session_minutes}분 · 5요소 공통 척도 ·{" "}
            <Link
              href="/admin/sample-report"
              className="text-accent underline-offset-4 hover:underline"
            >
              샘플 리포트 보기
            </Link>
          </p>
        )}
      </div>
      {error && (
        <p role="alert" className="text-danger">
          {error}
        </p>
      )}
      {actionError && (
        <p role="alert" className="text-danger">
          {actionError}
        </p>
      )}
      {result && <InviteResultBox title={result.title} result={result.value} />}
      {data && token && (
        <section className="flex flex-col gap-3">
          <h2 className="text-title2 font-semibold">지원자</h2>
          <CandidateTable
            candidates={data.candidates}
            onCancel={(c: Candidate) => run("취소", () => adminApi.cancel(token, c.session_id))}
            onReissue={(c) =>
              run(`${c.alias} 새 링크(재발급)`, () => adminApi.reissue(token, c.session_id))
            }
            onRetake={(c) =>
              run(`${c.alias} 재응시 초대 링크`, () =>
                adminApi.invite(token, id, { email: c.email, previous_session_id: c.session_id }),
              )
            }
            onRegenerate={(c) =>
              run("리포트 다시 생성", () => adminApi.regenerate(token, c.session_id))
            }
          />
        </section>
      )}
      <section className="flex flex-col gap-3 border-t border-line pt-6">
        <h2 className="text-title2 font-semibold">지원자 초대</h2>
        <InviteForm
          key={formKey}
          takenAliases={data?.candidates.map((c) => c.alias) ?? []}
          pending={pending}
          error={inviteError}
          onInvite={invite}
        />
      </section>
      <Toaster />
    </>
  );
}
