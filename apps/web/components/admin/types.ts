// /admin 응답 형태. 정본은 docs/common/contracts.md이고, 계약에 열려 있는 필드는 선택으로 둔다.
import type { DisplayStatus } from "@/components/ui";

export type RubricRef = { id: string; text: string; pilot_value: boolean };

export type CatalogElement = {
  id: string;
  name: string;
  situation_public: string;
  rubric: RubricRef[];
};

export type Catalog = {
  elements: CatalogElement[];
  timeline: { flow: { card_id: string; at_fraction: number }[]; element_fraction_rule: string };
  candidate_notice_template: string;
  session_minutes: number;
};

export type Position = {
  id: string;
  name: string;
  elements: string[];
  candidate_count: number;
  created_at: string;
};

export type Tally = { met: number; judged: number; no_record: number };

export type CandidateScore = Tally & {
  source: "auto" | "reviewer";
  by_element: { element: string; met: number; judged: number }[];
};

export type Candidate = {
  session_id: string;
  alias: string;
  status: string;
  display_status: DisplayStatus;
  invited_at: string;
  report_ready_at: string | null;
  failed_stage?: string;
  failed_reason?: string;
  previous_session_id?: string;
  score: CandidateScore | null;
};

export type InviteResult = {
  session_id: string;
  invite_url: string;
  expires_at: string;
  notice_text: string;
};

/** 평가표 항목 값: 1 충족, 0 미충족, null 기록 없음 */
export type ItemValue = 1 | 0 | null;

export type Evidence = {
  type: "message" | "revision" | "doc_view" | "assistant_call";
  id: string;
  t_min: number;
  channel?: string;
  quote?: string;
  part_no?: number;
  summary?: string;
  change_ratio?: number;
  context?: { prev_persona_message?: string | null; card_at_t_min?: number | null };
};

export type RubricItem = {
  id: string;
  text: string;
  auto: ItemValue;
  reviewer: ItemValue;
  memo: string | null;
  adjusted?: boolean;
  no_record_reason?: string;
  /** 응답 시간 항목의 실제 분 */
  minutes?: number;
  evidence: { type: string; id: string; t_min?: number }[];
};

export type RubricElement = {
  element: string;
  name: string;
  auto: Tally;
  reviewer: Tally | null;
  items: RubricItem[];
};

export type HistoryRow = {
  item_id: string;
  element: string;
  auto: ItemValue;
  reviewer: ItemValue;
  memo: string;
  created_at: string;
};

export type Fact = string | { text: string };

export type ReportSection = {
  element: string;
  name: string;
  situation: string;
  card_t_min?: number;
  event_fired?: boolean;
  observed: string | null;
  note?: string;
  no_record_reason?: string;
  evidence: Evidence[];
  aux_facts?: Fact[];
  out_of_window_messages?: { t_min: number; channel?: string; quote: string }[];
};

export type AiEvidence = {
  call_id: string;
  t_min: number;
  quote?: string;
  part_no?: number;
  reuse?: string;
  /** 위임·맥락·검증 구분. 없으면 "기타" */
  category?: "delegate" | "context" | "verify";
};

export type Report = {
  session_id: string;
  alias: string;
  stage: "draft" | "final";
  position: { name: string; elements: string[] };
  deliverable: {
    parts: {
      part_no: number;
      title: string;
      assignee: string | null;
      content: string;
      revisions: number;
      empty: boolean;
    }[];
    division_decided_by: string | null;
    final_report_message: { id: string; t_min: number; content: string } | null;
  };
  rubric: {
    elements: RubricElement[];
    auto_total: Tally;
    reviewer_total: Tally | null;
    review: { memo: string | null; reviewed_at: string | null } | null;
    history: HistoryRow[];
  };
  sections: ReportSection[];
  ai_usage: { used: boolean; summary: string; evidence: AiEvidence[] };
  generated_at: string;
  reviewed_at: string | null;
};

export type Adjustment = { item_id: string; value: ItemValue; memo: string };
