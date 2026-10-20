// 지원자 화면이 쓰는 계약 형태. 정본은 docs/common/contracts.md(지원자 REST·State·WebSocket).

export type SessionStatus =
  | "invited"
  | "cancelled"
  | "in_progress"
  | "reporting"
  | "completed"
  | "report_ready"
  | "approving"
  | "reviewed"
  | "failed";

/** GET /s/{token} */
export type Entry = {
  company_name: string;
  duration_minutes: number;
  status: SessionStatus;
  elements_names: string[];
  entry_notice: string;
  contact_email: string;
  debrief_token?: string;
  failed_stage?: "session" | "report";
};

export type Channel = "team" | "dm" | "manager_dm" | "notice";
export type Sender = "candidate" | "colleague" | "manager" | "system";
export type DocRef = { doc_id: string; version: number };

export type Message = {
  id: string;
  channel: Channel;
  sender: Sender;
  content: string;
  event_id: string | null;
  run_id: string | null;
  t_min: number;
  created_at: string;
  reply_to_doc?: DocRef | null;
  shared_doc?: DocRef | null;
};

export type MyVersion = {
  version: number;
  revision: number;
  channel: "team" | "dm";
  message_id: string;
  t_min: number;
};

export type MyDocument = {
  doc_id: string;
  part_no: number;
  title: string;
  content: string;
  updated_at: string;
  revision: number;
  versions: MyVersion[];
};

export type ReceivedVersion = {
  version: number;
  channel: "team" | "dm";
  message_id: string;
  t_min: number;
  opened: boolean;
};

export type ReceivedDocument = {
  doc_id: string;
  owner: "colleague";
  part_no: number;
  title: string;
  versions: ReceivedVersion[];
};

export type FinalSection = {
  part_no: number;
  title: string;
  content: string;
  source_doc_id: string | null;
  source_version: number | null;
  edited: boolean;
};

export type Assignee = "candidate" | "colleague" | "both";
export type TaskStatus = "todo" | "doing" | "done";

export type Task = {
  part_no: number;
  assignee: Assignee | null;
  status: TaskStatus;
  order: number;
  due_min: number | null;
  depends_on: number[];
};

export type CompanyDoc = {
  doc_id: string;
  title: string;
  released: boolean;
  release_at_min: number | null;
};

export type AssistantCall = {
  call_id: string;
  request: string;
  response: string;
  cited_docs: string[];
  t_min: number;
};

export type Gap = { from_t_min: number; to_t_min: number };

export type Division = {
  parts: Record<string, Assignee>;
  decided_by: "candidate" | "colleague_default";
  decided_at: string;
};

/** GET /sessions/{id}/state */
export type StateSnapshot = {
  session: {
    id: string;
    /** 초대 별칭(contracts State). 없으면 킥오프 문장에서 읽는다 */
    alias?: string;
    status: SessionStatus;
    started_at: string | null;
    ends_at: string | null;
    remaining_seconds: number | null;
    deadline_at: string | null;
    completed_at: string | null;
  };
  division: Division | null;
  messages: Message[];
  my_documents: MyDocument[];
  received: ReceivedDocument[];
  final: { sections: FinalSection[]; template: { length: string } };
  tasks: Task[];
  documents: CompanyDoc[];
  assistant: AssistantCall[];
  active_runs: { run_id: string; actor: Actor; node: string }[];
  connection_gaps: Gap[];
  channels: Record<Channel, { members: Sender[] }>;
  persona: { manager: string; colleague: string; candidate_role: string };
};

export type Actor = "colleague" | "manager" | "assistant";

/** POST /sessions/{id}/documents/{doc_id}/open */
export type OpenedDocument = {
  doc_id: string;
  owner: "colleague";
  part_no: number;
  title: string;
  version: number;
  content: string;
  t_min: number;
};

export type AssistantReply = {
  call_id: string;
  message_id: string;
  content: string;
  cited_docs: string[];
};

export type DebriefEvent = {
  card_id: string;
  element: string;
  name: string;
  description: string;
  rubric_items: string[];
};

/** GET /sessions/{id}/debrief */
export type Debrief = {
  events: DebriefEvent[];
  persona_note: string | null;
  scoring_notice: string;
  connection_gaps?: Gap[];
  retention_notice?: string;
  contact_email?: string;
  final: { sections: { part_no: number; title: string; content: string }[] } | null;
  final_view_until: string | null;
  survey: { submitted: boolean; questions: { q: string; text: string }[] };
  failed_stage?: "session" | "report";
};

type Frame<T extends string, P> = { type: T; payload: P };

export type ServerFrame =
  | Frame<"message.ack", { client_msg_id: string; message_id: string; run_id: string }>
  | Frame<"message.new", Message>
  | Frame<
      "agent.progress",
      {
        run_id: string;
        actor: Actor;
        node: string;
        status: "started" | "tool_start" | "tool_end" | "finished" | "failed";
        tool?: string;
      }
    >
  | Frame<"document.released", { doc_id: string; title: string }>
  | Frame<
      "document.shared",
      {
        doc_id: string;
        version: number;
        part_no: number;
        by: "candidate" | "colleague";
        channel: "team" | "dm";
        message_id: string;
      }
    >
  | Frame<
      "task.updated",
      Omit<Task, "depends_on"> & { by: "candidate" | "colleague"; depends_on?: number[] }
    >
  | Frame<
      "division.confirmed",
      { parts: Record<string, Assignee>; decided_by: Division["decided_by"]; t_min: number }
    >
  | Frame<"session.reporting", { deadline_at: string }>
  | Frame<"session.ended", { reason: "submitted" | "timeout" | "failed" | "cancelled" }>
  | Frame<"session.replaced", Record<string, never>>
  | Frame<"error", { code: string; message: string }>;

export type SendFrame = {
  type: "message.send";
  payload: {
    client_msg_id: string;
    channel: "team" | "dm" | "manager_dm";
    content: string;
    reply_to_doc?: DocRef;
  };
};
