"use client";

import Link from "next/link";

import { adminApi, useLoad } from "@/components/admin/client";
import { PositionList } from "@/components/admin/position-list";
import type { Catalog, Position } from "@/components/admin/types";
import { Button } from "@/components/ui";

export default function PositionsPage() {
  const { data, error } = useLoad<{ positions: Position[]; catalog: Catalog }>(async (token) => {
    const [positions, catalog] = await Promise.all([
      adminApi.positions(token),
      adminApi.catalog(token),
    ]);
    return { positions, catalog };
  });

  return (
    <>
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">채용 건</h1>
        <Link href="/admin/positions/new">
          <Button>채용 건 만들기</Button>
        </Link>
      </div>
      {error && (
        <p role="alert" className="text-danger">
          {error}
        </p>
      )}
      {data && <PositionList positions={data.positions} catalog={data.catalog} />}
    </>
  );
}
