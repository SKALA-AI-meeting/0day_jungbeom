// 채용 건 목록: 이름, 요소, 지원자 수(초대한 사람 수), 생성 시각.
import Link from "next/link";

import { Badge, Button, Card, EmptyState } from "@/components/ui";

import { formatDateTime } from "./format";
import type { Catalog, Position } from "./types";

export function PositionList({ positions, catalog }: { positions: Position[]; catalog: Catalog }) {
  const names = new Map(catalog.elements.map((e) => [e.id, e.name]));
  if (positions.length === 0) {
    return (
      <Card>
        <EmptyState
          title="아직 채용 건이 없습니다"
          description="관찰 요소를 골라 첫 채용 건 만들기"
          action={
            <Link href="/admin/positions/new">
              <Button>채용 건 만들기</Button>
            </Link>
          }
        />
      </Card>
    );
  }
  return (
    <ul className="flex flex-col gap-3">
      {positions.map((position) => (
        <li key={position.id}>
          <Link href={`/admin/positions/${position.id}`} className="block">
            <Card
              title={position.name}
              actions={
                <span className="shrink-0 text-sm text-muted">
                  지원자 {position.candidate_count}명
                </span>
              }
              className="hover:bg-surface-sunken"
            >
              <div className="flex flex-wrap items-center gap-2">
                {position.elements.map((id) => (
                  <Badge key={id} tone="accent">
                    {names.get(id) ?? id}
                  </Badge>
                ))}
                <span className="ml-auto text-sm text-subtle">
                  {formatDateTime(position.created_at)} 생성
                </span>
              </div>
            </Card>
          </Link>
        </li>
      ))}
    </ul>
  );
}
