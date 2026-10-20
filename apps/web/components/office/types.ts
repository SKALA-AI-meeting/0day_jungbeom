// 지원자 화면이 쓰는 계약 타입. 정본은 docs/common/contracts.md의 "지원자 REST"·State·WebSocket 절.

export type SessionStatus =
  "invited" | "in_progress" | "completed" | "report_ready" | "approving" | "reviewed" | "failed";

/** GET /s/{token} */
export type Entry = {
  company_name: string;
  duration_minutes: number;
  status: SessionStatus;
  elements_names: string[];
  entry_notice: string;
  debrief_token?: string;
  failed_stage?: "session" | "report" | null;
};

export type Channel = "team" | "dm" | "notice";
export type Sender = "candidate" | "colleague" | "manager" | "system";

export type Message = {
  id: string;
  channel: Channel;
  sender: Sender;
  content: string;
  event_id: string | null;
  run_id: string | null;
  t_min: number | null;
  created_at: string;
};

export type Assignee = "candidate" | "colleague" | "both";
export type TaskStatus = "todo" | "doing" | "done";

export type Part = { content: string; revision: number; updated_by: string | null };
export type Task = { part_no: number; assignee: Assignee; status: TaskStatus };
export type CompanyDoc = { doc_id: string; title: string; released: boolean };
export type AssistantCall = {
  call_id: string;
  request: string;
  response: string | null;
  cited_docs: string[];
  t_min: number | null;
};
export type Actor = "colleague" | "manager" | "assistant";
export type ActiveRun = { run_id: string; actor: Actor; node: string };

/** GET /sessions/{id}/state */
export type StateSnapshot = {
  session: {
    id: string;
    status: SessionStatus;
    started_at: string | null;
    ends_at: string | null;
    remaining_seconds: number | null;
  };
  messages: Message[];
  document: Record<string, Part>;
  tasks: Task[];
  documents: CompanyDoc[];
  assistant: AssistantCall[];
  active_runs: ActiveRun[];
  persona: { manager: string; colleague: string };
};

export type ProgressStatus = "started" | "tool_start" | "tool_end" | "finished" | "failed";

/** 서버 → 클라이언트 프레임. 봉투는 {type, payload}. */
export type ServerFrame =
  | { type: "message.ack"; payload: { client_msg_id: string; message_id: string; run_id: string } }
  | { type: "message.new"; payload: Message }
  | {
      type: "agent.progress";
      payload: {
        run_id: string;
        actor: Actor;
        node: string;
        status: ProgressStatus;
        tool?: string;
      };
    }
  | { type: "document.released"; payload: { doc_id: string; title: string } }
  | {
      type: "document.part_updated";
      payload: { part_no: number; content: string; revision: number; by: "colleague" };
    }
  | { type: "task.updated"; payload: Task }
  | { type: "session.ended"; payload: { reason: "submitted" | "timeout" | "failed" } }
  | { type: "session.replaced"; payload: Record<string, never> }
  | { type: "error"; payload: { code: string; message: string } };

export type SendFrame = {
  type: "message.send";
  payload: { client_msg_id: string; channel: "team" | "dm"; content: string };
};

/** POST /sessions/{id}/assistant */
export type AssistantReply = {
  call_id: string;
  message_id: string;
  content: string;
  cited_docs: string[];
};

/** GET /sessions/{id}/debrief */
export type Debrief = {
  events: { element: string; name: string; description: string; rubric_items: string[] }[];
  persona_note: string | null;
  scoring_notice: string;
  failed_stage?: "session" | "report";
};
