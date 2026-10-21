"use client";

import Link from "next/link";

import { adminApi, useLoad } from "@/components/admin/client";
import { PositionList } from "@/components/admin/position-list";
import { Button } from "@/components/ui";

export default function PositionsPage() {
  const { data, error } = useLoad(adminApi.positions);

  return (
    <>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-title1 font-bold">채용 건</h1>
        <div className="flex items-center gap-3">
          <Link
            href="/admin/sample-report"
            className="text-sm text-accent underline-offset-4 hover:underline"
          >
            샘플 리포트 보기
          </Link>
          <Link href="/admin/positions/new">
            <Button>채용 건 만들기</Button>
          </Link>
        </div>
      </div>
      {error && (
        <p role="alert" className="text-danger">
          {error}
        </p>
      )}
      {data && <PositionList positions={data} />}
    </>
  );
}
