// 채용 건 목록: 이름, 세션 길이, 지원자 수, 생성 시각. 얇은 행 구분선의 표.
import Link from "next/link";

import { Button, EmptyState } from "@/components/ui";

import { formatDateTime } from "./format";
import type { Position } from "./types";

export function PositionList({ positions }: { positions: Position[] }) {
  if (positions.length === 0) {
    return (
      <EmptyState
        title="아직 채용 건이 없습니다"
        action={
          <Link href="/admin/positions/new">
            <Button>채용 건 만들기</Button>
          </Link>
        }
      />
    );
  }
  return (
    <table className="w-full border-y border-line text-left">
      <thead className="text-sm text-muted">
        <tr className="border-b border-line">
          <th className="py-2 font-medium">이름</th>
          <th className="py-2 font-medium">세션 길이</th>
          <th className="py-2 font-medium">지원자</th>
          <th className="py-2 font-medium">만든 시각</th>
        </tr>
      </thead>
      <tbody className="divide-y divide-line">
        {positions.map((p) => (
          <tr key={p.id}>
            <td className="py-3 pr-4">
              <Link
                href={`/admin/positions/${p.id}`}
                className="font-semibold break-all text-accent underline-offset-4 hover:underline"
              >
                {p.name}
              </Link>
            </td>
            <td className="py-3 pr-4 tabular-nums">
              {p.session_minutes}분{p.session_minutes === 15 && " (데모)"}
            </td>
            <td className="py-3 pr-4 tabular-nums">{p.candidate_count}명</td>
            <td className="py-3 text-sm text-muted tabular-nums">{formatDateTime(p.created_at)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
