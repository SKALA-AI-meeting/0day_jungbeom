// 관리자 화면이 쓰는 계약 형태. 정본은 docs/common/contracts.md "관리자 REST"와 Report.

export type ElementId =
  "responsibility" | "planning" | "adaptability" | "collaboration" | "honesty";

export type CatalogElement = {
  id: ElementId;
  name: string;
  meaning: string;
  how_we_see: string;
  if_unselected: string;
};

export type Catalog = {
  missions: { id: string; name: string; company_name: string; deliverable: string }[];
  elements: CatalogElement[];
  candidate_notice_template: string;
  candidate_faq: { q: string; a: string }[];
  session_minutes: number;
};

export type Position = {
  id: string;
  name: string;
  mission_id: string;
  elements: ElementId[];
  candidate_count: number;
  created_at: string;
};

export type DisplayGroup = "waiting" | "in_progress" | "needs_review" | "done" | "problem";

export type Counts = { met: number; unmet: number; no_record: number };

export type Candidate = {
  session_id: string;
  alias: string;
  email: string;
  status: string;
  display_status: string;
  display_group: DisplayGroup;
  invited_at: string;
  started_at?: string | null;
  ends_at?: string | null;
  last_activity_at?: string | null;
  message_count: number;
  report_ready_at?: string | null;
  purge_at?: string | null;
  failed_stage?: "session" | "report" | null;
  failed_reason?: string | null;
  next_action?: string | null;
  previous_session_id?: string | null;
  previous_relation?: "retry" | "reissue" | null;
  met: number | null;
  unmet: number | null;
  no_record: number | null;
  score_source: "auto" | "reviewer" | null;
  by_element: ({ element: ElementId } & Counts)[] | null;
};

export type InviteResult = {
  session_id: string;
  invite_url: string;
  expires_at: string;
  notice_text: string;
};

export type RecordRef = { type: string; id: string; t_min: number };

export type Evidence = {
  type: "message" | "document" | "share" | "open" | "task_event" | "doc_view" | "assistant_call";
  id: string;
  t_min: number;
  channel?: string;
  quote?: string;
  summary?: string;
  doc_id?: string;
  part_no?: number | "final";
  version?: number;
  flag?: "aux_fact" | "out_of_window";
  reply_to_doc?: { doc_id: string; version: number } | null;
  context?: { prev_persona_message: string | null; card_at_t_min: number | null };
  record_ref: RecordRef | null;
};

export type NoRecordReason =
  | "no_activity"
  | "classify_failed"
  | "window_missed"
  | "document_missing"
  | "not_applicable"
  | "event_not_fired";

export type RubricItem = {
  id: string;
  text: string;
  basis: "metric" | "label";
  auto: 1 | 0 | null;
  reviewer: 1 | 0 | null;
  memo: string | null;
  adjusted: boolean;
  no_record_reason: NoRecordReason | null;
  minutes?: number | null;
  evidence: Evidence[];
};

export type HonestyFacts = {
  shares: {
    doc_id: string;
    owner: "candidate" | "colleague";
    part_no: number;
    versions: { version: number; channel: string; t_min: number }[];
  }[];
  final_sections: {
    part_no: number;
    source_doc_id: string | null;
    source_version: number | null;
    edited: boolean;
  }[];
  tasks: { part_no: number; assignee: string | null; status: string }[];
  empty_sections: number[];
  tasks_not_done: number[];
  changed_after_adaptability: boolean | null;
};

export type ReportCard = {
  card_id: string;
  name: string;
  /** 관찰 창(세션 분). 끊김 겹침·"판정 창에 메시지 없음" 표시에 쓴다 */
  window?: { start_min: number; end_min: number };
  situation: string;
  event_fired: boolean;
  card_at_t_min: number | null;
  observed: string | null;
  no_record_reason: NoRecordReason | null;
  note: string | null;
  evidence: Evidence[];
  facts?: HonestyFacts;
};

export type FinalSectionReport = {
  part_no: number;
  title: string;
  content: string;
  source_doc_id: string | null;
  source_owner: "candidate" | "colleague" | null;
  source_version: number | null;
  edited: boolean;
  source_content: string | null;
};

export type ReportDocument = {
  doc_id: string;
  owner: "candidate" | "colleague";
  part_no: number;
  title: string;
  versions: number;
  shares: { version: number; channel: string; t_min: number }[];
  empty?: boolean;
  opened_by_candidate?: number[];
};

export type ReviewInfo = { memo: string | null; reviewer_name: string; reviewed_at: string | null };

export type Note = { id: string; text: string; reviewer_name: string; created_at: string };

export type Report = {
  session_id: string;
  alias: string;
  stage: "draft" | "final";
  position: { name: string; mission_id: string; elements: ElementId[] };
  summary: ({ element: ElementId; name: string; line: string | null } & Counts)[];
  deliverable: {
    final: { sections: FinalSectionReport[]; submitted_version: number };
    documents: ReportDocument[];
    division_decided_by: "candidate" | "colleague_default" | null;
    final_report_message: { id: string; t_min: number; content: string } | null;
  };
  rubric: {
    elements: {
      element: ElementId;
      name: string;
      auto: Counts;
      cards: { card_id: string; name: string; items: RubricItem[] }[];
    }[];
    auto_total: Counts;
    reviewer_total: Counts | null;
    review: ReviewInfo | null;
  };
  sections: { element: ElementId; name: string; cards: ReportCard[] }[];
  ai_usage: {
    used: boolean;
    events: {
      call_id: string;
      t_min: number;
      request_quote: string;
      response_quote: string;
      cited_doc_ids: string[];
      applied_part: number | "final" | null;
    }[];
  };
  notes: Note[];
  connection_gaps: { from_t_min: number; to_t_min: number }[];
  generated_at: string;
  reviewed_at: string | null;
  purge_at: string;
};

export type Adjustment = { item_id: string; value: 1 | 0 | null; memo: string };

export type RecordEntry = {
  t_min: number;
  type:
    "message" | "share" | "open" | "task_event" | "assistant_call" | "notice" | "connection_gap";
  channel?: string;
  by: string;
  summary: string;
  ref: RecordRef;
};
