"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";

import { adminApi, errorMessage, useLoad, useToken } from "@/components/admin/client";
import { CandidateTable, InvitePanel } from "@/components/admin/candidates";
import type { InvitePrefill } from "@/components/admin/candidates";
import type { Candidate, Catalog, InviteResult, Position } from "@/components/admin/types";
import { Button, Card } from "@/components/ui";

export default function PositionDetailPage() {
  const { id } = useParams<{ id: string }>();
  const token = useToken();
  const { data, error, reload } = useLoad<{
    position: Position | undefined;
    candidates: Candidate[];
    catalog: Catalog;
  }>(async (t) => {
    const [positions, candidates, catalog] = await Promise.all([
      adminApi.positions(t),
      adminApi.candidates(t, id),
      adminApi.catalog(t),
    ]);
    return { position: positions.find((p) => p.id === id), candidates, catalog };
  }, id);
  const [pending, setPending] = useState(false);
  const [inviteError, setInviteError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [result, setResult] = useState<InviteResult | null>(null);
  const [prefill, setPrefill] = useState<InvitePrefill | null>(null);

  async function invite(value: { alias: string; email: string; previous_session_id?: string }) {
    if (!token) return;
    setPending(true);
    setInviteError(null);
    try {
      setResult(await adminApi.invite(token, id, value));
      setPrefill(null);
      reload();
    } catch (e) {
      setInviteError(errorMessage(e));
    } finally {
      setPending(false);
    }
  }

  async function regenerate(candidate: Candidate) {
    if (!token) return;
    setActionError(null);
    try {
      await adminApi.regenerate(token, candidate.session_id);
    } catch (e) {
      setActionError(errorMessage(e));
    }
    reload();
  }

  async function cancel(candidate: Candidate) {
    if (!token) return;
    setActionError(null);
    try {
      await adminApi.cancel(token, candidate.session_id);
    } catch (e) {
      setActionError(errorMessage(e));
    }
    reload();
  }

  const names = new Map(data?.catalog.elements.map((e) => [e.id, e.name]));
  return (
    <>
      <div>
        <Link href="/admin/positions" className="text-sm text-muted hover:underline">
          ← 채용 건 목록
        </Link>
        <h1 className="mt-1 text-2xl font-semibold">{data?.position?.name ?? "채용 건"}</h1>
        {data?.position && (
          <p className="text-sm text-muted">
            요소 {data.position.elements.length}개:{" "}
            {data.position.elements.map((e) => names.get(e) ?? e).join(", ")} ·{" "}
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
      {data && (
        <Card
          title="지원자"
          actions={
            <a href="#invite">
              <Button size="sm" variant="secondary">
                지원자 초대
              </Button>
            </a>
          }
        >
          <CandidateTable
            candidates={data.candidates}
            names={names}
            onCancel={cancel}
            onRegenerate={regenerate}
            onReinvite={(c) => {
              setResult(null);
              setPrefill({
                alias: c.alias,
                email: c.email,
                previous_session_id: c.session_id,
                relation: c.display_status === "expired" ? "초대 연장" : "다시 초대",
              });
            }}
          />
        </Card>
      )}
      {/* 초대에 성공하면 key가 바뀌어 폼이 비워진다(방금 만든 별칭이 중복으로 보이지 않게) */}
      <div id="invite" className="scroll-mt-6" />
      <InvitePanel
        key={`${prefill?.previous_session_id ?? "new"}-${result?.session_id ?? ""}`}
        prefill={prefill}
        takenAliases={data?.candidates.map((c) => c.alias) ?? []}
        onClearPrefill={() => setPrefill(null)}
        pending={pending}
        error={inviteError}
        result={result}
        onInvite={invite}
      />
    </>
  );
}
